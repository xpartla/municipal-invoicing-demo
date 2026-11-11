"""What the intake use cases return."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from riso.identity import Permission
from riso.intake.application.ports import EInvoiceReader
from riso.intake.application.uow import IntakeUnitOfWork
from riso.intake.domain import Document, MediaType
from riso.intake.domain.einvoice import EInvoiceReading
from riso.intake.domain.extract import Evidence
from riso.intake.domain.extraction import Extraction
from riso.intake.domain.layout import ReadingFailed
from riso.intake.domain.note import NoteSuggestions
from riso.invoicing import counter_hint
from riso.shared.clock import local_date
from riso.shared.context import RequestContext
from riso.shared.errors import NotFound
from riso.shared.ports import FileStorage


@dataclass(frozen=True, slots=True)
class DocumentView:
    id: str
    filename: str
    media_type: MediaType
    size: int
    pages: int | None
    uploaded_at: datetime
    uploaded_by: str | None
    invoice_id: str | None

    @classmethod
    def of(cls, document: Document, invoice_id: str | None) -> "DocumentView":
        return cls(
            id=document.id,
            filename=document.filename,
            media_type=document.media_type,
            size=document.size,
            pages=document.pages,
            uploaded_at=document.uploaded_at,
            uploaded_by=document.uploaded_by,
            invoice_id=invoice_id,
        )


@dataclass(frozen=True, slots=True)
class UploadOutcome:
    """One file of an upload: taken (its document, invoice and extraction job), or refused
    with the reason's code (`file_empty`, `file_too_large`, `file_type`, `too_many_pages`,
    `duplicate`) and, for a duplicate, the invoice the same file became."""

    filename: str
    status: Literal["accepted", "rejected"]
    document_id: str | None = None
    invoice_id: str | None = None
    job_id: str | None = None
    reason: str | None = None
    message: str | None = None
    duplicate_of: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentFile:
    data: bytes
    media_type: MediaType
    filename: str


@dataclass(frozen=True, slots=True)
class ExtractionView:
    id: str
    document_id: str
    invoice_id: str
    engine: str
    engine_version: str
    source: str
    created_at: datetime
    duration_ms: int
    pages: int
    warnings: tuple[str, ...]
    confidence: dict[str, float]
    evidence: dict[str, Evidence]
    note: NoteSuggestions | None
    note_image: bool = False
    number_preview: int | None = None

    @classmethod
    def of(cls, extraction: Extraction, number_preview: int | None = None) -> "ExtractionView":
        return cls(
            id=extraction.id,
            document_id=extraction.document_id,
            invoice_id=extraction.invoice_id,
            engine=extraction.engine,
            engine_version=extraction.engine_version,
            source=extraction.source,
            created_at=extraction.created_at,
            duration_ms=extraction.duration_ms,
            pages=len(extraction.page_keys),
            warnings=extraction.warnings,
            confidence=dict(extraction.document.ocr_meta.confidence),
            evidence=dict(extraction.evidence),
            note=extraction.note,
            note_image=extraction.note_key is not None,
            number_preview=number_preview,
        )


def _latest(uow: IntakeUnitOfWork, customer_id: str, document_id: str) -> Extraction:
    uow.documents.get(customer_id, document_id)  # NotFound for another customer's document
    extraction = uow.extractions.latest(customer_id, document_id)
    if extraction is None:
        raise NotFound(f"document {document_id} has not been read")
    return extraction


def get_extraction(
    ctx: RequestContext, uow: IntakeUnitOfWork, customer_id: str, document_id: str
) -> ExtractionView:
    """The document's newest reading: what the check step shows next to its pages."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        extraction = _latest(uow, customer_id, document_id)
        preview = None
        if extraction.source == "einvoice":
            # The number booking would give now in the default series, the year being the
            # suggested booking date's (the upload's); decision 65 shows it, never fills it.
            dates = extraction.note.date if extraction.note is not None else ()
            year = int(dates[0].value[:4]) if dates else local_date(extraction.created_at).year
            preview, _ = counter_hint(uow, customer_id, year)
        return ExtractionView.of(extraction, preview)


MAX_XML_SHOWN = 1_000_000
"""Characters of the raw XML the viewer gets; the file itself is downloaded whole."""


@dataclass(frozen=True, slots=True)
class EInvoiceDetail:
    reading: EInvoiceReading | None
    failure: str | None
    xml: str
    truncated: bool


def einvoice_detail(
    ctx: RequestContext,
    uow: IntakeUnitOfWork,
    storage: FileStorage,
    einvoices: EInvoiceReader,
    customer_id: str,
    document_id: str,
) -> EInvoiceDetail:
    """The e-invoice the document is or carries, read again from its file, for the viewer's
    rendered view and raw XML (plan §8.4). An XML file that cannot be read gives its raw text
    and the failure's reason; a document that is no e-invoice is not found."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        document = uow.documents.get(customer_id, document_id)
    if document.media_type not in (MediaType.XML, MediaType.PDF):
        raise NotFound(f"document {document_id} is not an e-invoice")
    with storage.open(document.storage_key) as handle:
        data = handle.read()
    reading: EInvoiceReading | None = None
    failure: str | None = None
    xml = data if document.media_type is MediaType.XML else b""
    try:
        if document.media_type is MediaType.XML:
            reading = einvoices.read_xml(data)
        else:
            found = einvoices.read_pdf(data)
            if found is None:
                raise NotFound(f"document {document_id} carries no e-invoice")
            reading, xml = found
    except ReadingFailed as failed:
        failure = failed.reason
    text = xml.decode("utf-8", errors="replace")
    return EInvoiceDetail(
        reading, failure, text[:MAX_XML_SHOWN], truncated=len(text) > MAX_XML_SHOWN
    )


def extraction_image(
    ctx: RequestContext,
    uow: IntakeUnitOfWork,
    storage: FileStorage,
    customer_id: str,
    document_id: str,
    page: int | None,
) -> bytes:
    """A page as read (JPEG), or with `page` None the note's crop (PNG)."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        extraction = _latest(uow, customer_id, document_id)
    if page is None:
        key = extraction.note_key
    else:
        key = extraction.page_keys[page] if 0 <= page < len(extraction.page_keys) else None
    if key is None:
        raise NotFound("no such image of the reading")
    with storage.open(key) as handle:
        return handle.read()
