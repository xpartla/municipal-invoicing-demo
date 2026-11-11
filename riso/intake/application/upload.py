"""Uploading invoices (plan §8.2, §8.4, §10.5, decision 18): several files at once, each on
its own. A file is taken when its content is a PDF, JPEG, PNG, TIFF or XML of at most 20 MB
and 5 pages (a PDF carrying an e-invoice may have more) that the customer has not uploaded
before (plan §7.3, by SHA-256). Taking it stores the
file, records the `Document`, creates its invoice and queues the `extract_document` job, in
one transaction; a refused file changes nothing.
"""

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from riso.identity import Permission
from riso.intake.application.extraction import EXTRACT_JOB, ExtractDocument
from riso.intake.application.ports import EInvoiceReader, PageCounter
from riso.intake.application.uow import IntakeUnitOfWork
from riso.intake.application.views import DocumentFile, DocumentView, UploadOutcome
from riso.intake.domain import (
    MAX_BYTES,
    MAX_PAGES,
    SNIFF_BYTES,
    Document,
    MediaType,
    check_upload,
    safe_filename,
    sniff,
)
from riso.intake.domain.layout import ReadingFailed
from riso.invoicing import invoice_of_document, register_upload
from riso.shared.context import RequestContext
from riso.shared.errors import ValidationFailed
from riso.shared.ports import FileStorage

MAX_FILES = 20
"""Files in one upload request."""


@dataclass(frozen=True, slots=True)
class UploadedFile:
    filename: str | None
    data: bytes
    truncated: bool = False
    """The request held more than `MAX_BYTES` of it; only that much was read."""


def channel_of(media_type: MediaType) -> str:
    """XML is an e-invoice, images are scans. A PDF is taken as a scan too until its
    extraction finds an e-invoice attached (P2-M6) or a usable text layer, which makes it a
    digital PDF (P2-M5-T04)."""
    return "einvoice" if media_type is MediaType.XML else "scan"


def _carries_einvoice(einvoices: EInvoiceReader | None, data: bytes) -> bool:
    if einvoices is None:
        return False
    try:
        return einvoices.read_pdf(data) is not None
    except ReadingFailed:
        return False


def upload_documents(
    ctx: RequestContext,
    uow_factory: Callable[[], IntakeUnitOfWork],
    storage: FileStorage,
    counter: PageCounter,
    customer_id: str,
    files: Sequence[UploadedFile],
    einvoices: EInvoiceReader | None = None,
) -> list[UploadOutcome]:
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    if not files:
        raise ValidationFailed.on("files", "no file", "no_files")
    if len(files) > MAX_FILES:
        raise ValidationFailed.on("files", f"at most {MAX_FILES} files at once", "too_many_files")
    return [
        _upload(ctx, uow_factory(), storage, counter, customer_id, file, einvoices)
        for file in files
    ]


def _upload(
    ctx: RequestContext,
    uow: IntakeUnitOfWork,
    storage: FileStorage,
    counter: PageCounter,
    customer_id: str,
    file: UploadedFile,
    einvoices: EInvoiceReader | None = None,
) -> UploadOutcome:
    name = safe_filename(file.filename)
    size = MAX_BYTES + 1 if file.truncated else len(file.data)
    try:
        media_type = check_upload(size, sniff(file.data[:SNIFF_BYTES]), None)
        pages = counter.pages(file.data, media_type)
        long_einvoice = (
            media_type is MediaType.PDF
            and pages is not None
            and pages > MAX_PAGES
            and _carries_einvoice(einvoices, file.data)
        )
        check_upload(size, media_type, pages, einvoice=long_einvoice)
    except ValidationFailed as refused:
        error = refused.errors[0]
        return UploadOutcome(name, "rejected", reason=error.code, message=error.message)
    sha256 = hashlib.sha256(file.data).hexdigest()

    with uow:
        existing = uow.documents.by_sha256(customer_id, sha256)
        if existing is not None:
            return UploadOutcome(
                name,
                "rejected",
                document_id=existing.id,
                reason="duplicate",
                message="the same file was uploaded before",
                duplicate_of=invoice_of_document(uow, customer_id, existing.id),
            )
        stored = storage.put(file.data, owner=customer_id, extension=media_type.extension)
        try:
            at = uow.clock.now()
            document = Document.uploaded(
                uow.ids.new(),
                customer_id,
                sha256=sha256,
                filename=name,
                media_type=media_type,
                size=size,
                pages=pages,
                storage_key=stored.key,
                at=at,
                actor_id=ctx.actor_id,
                einvoice=long_einvoice,
            )
            uow.documents.add(document)
            invoice_id = uow.ids.new()
            payload = ExtractDocument(
                customer_id=customer_id, document_id=document.id, invoice_id=invoice_id
            )
            job_id = uow.queue.enqueue(
                EXTRACT_JOB,
                payload.model_dump(),
                customer_id=customer_id,
                created_by=ctx.actor_id,
            )
            register_upload(
                ctx,
                uow,
                customer_id,
                invoice_id=invoice_id,
                document_id=document.id,
                channel=channel_of(media_type),
                job_id=job_id,
                source_ref=name,
            )
            uow.audit.record(
                ctx,
                "document.uploaded",
                target_type="document",
                target_id=document.id,
                customer_id=customer_id,
                details={"media_type": media_type.value, "size": size, "pages": pages},
            )
            uow.commit()
        except BaseException:
            if stored.created:
                storage.delete(stored.key)
            raise
    return UploadOutcome(
        name, "accepted", document_id=document.id, invoice_id=invoice_id, job_id=job_id
    )


def get_document(
    ctx: RequestContext, uow: IntakeUnitOfWork, customer_id: str, document_id: str
) -> DocumentView:
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        document = uow.documents.get(customer_id, document_id)
        return DocumentView.of(document, invoice_of_document(uow, customer_id, document.id))


def customer_documents(
    ctx: RequestContext, uow: IntakeUnitOfWork, customer_id: str
) -> list[DocumentView]:
    """Every document of the customer with the invoice it became, the newest first (the
    storage listing)."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        return [
            DocumentView.of(d, invoice_of_document(uow, customer_id, d.id))
            for d in uow.documents.of_customer(customer_id)
        ]


def document_file(
    ctx: RequestContext,
    uow: IntakeUnitOfWork,
    storage: FileStorage,
    customer_id: str,
    document_id: str,
) -> DocumentFile:
    """The file as it was uploaded."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        document = uow.documents.get(customer_id, document_id)
    with storage.open(document.storage_key) as handle:
        data = handle.read()
    return DocumentFile(data, document.media_type, document.filename)
