"""The intake API: uploading invoices (several files at once), a document and its file."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Path, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from riso.api.deps import Caller, ServicesDep, check_csrf, customer_context
from riso.identity import Permission
from riso.intake.api.models import DocumentOut, UploadItemOut, UploadOut
from riso.intake.application import (
    MAX_FILES,
    UploadedFile,
    document_file,
    get_document,
    upload_documents,
)
from riso.intake.domain import MAX_BYTES
from riso.shared.errors import ValidationFailed

router = APIRouter(prefix="/api", dependencies=[Depends(check_csrf)], tags=["intake"])

Processor = Annotated[Caller, Depends(customer_context(Permission.INVOICES_PROCESS))]
Reader = Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))]
DocumentId = Annotated[str, Path(max_length=64)]


async def _read(file: UploadFile) -> UploadedFile:
    """At most `MAX_BYTES` and one more byte, to tell a file that is too large."""
    data = await file.read(MAX_BYTES + 1)
    return UploadedFile(file.filename, data[:MAX_BYTES], truncated=len(data) > MAX_BYTES)


@router.post("/customers/{customer_id}/documents", name="documents.upload")
async def upload(
    caller: Processor,
    services: ServicesDep,
    customer_id: str,
    files: Annotated[list[UploadFile], File(description="One invoice per file")],
) -> UploadOut:
    """Uploads invoices: PDF, JPEG, PNG or TIFF files of at most 20 MB and 5 pages, one
    invoice each, at most 20 per request. Each file is taken or refused on its own; a taken
    file becomes an invoice whose extraction job starts (poll `jobs.get_customer`)."""
    if len(files) > MAX_FILES:
        raise ValidationFailed.on("files", f"at most {MAX_FILES} files at once", "too_many_files")
    uploaded = [await _read(file) for file in files]
    outcomes = await run_in_threadpool(
        upload_documents,
        caller.ctx,
        services.uow,
        services.storage,
        services.pages,
        customer_id,
        uploaded,
    )
    items = [UploadItemOut.of(o) for o in outcomes]
    accepted = sum(item.status == "accepted" for item in items)
    return UploadOut(items=items, accepted=accepted, rejected=len(items) - accepted)


@router.get("/customers/{customer_id}/documents/{document_id}", name="documents.get")
def document(
    caller: Reader, services: ServicesDep, customer_id: str, document_id: DocumentId
) -> DocumentOut:
    return DocumentOut.of(
        get_document(caller.ctx, services.uow(immediate=False), customer_id, document_id)
    )


@router.get("/customers/{customer_id}/documents/{document_id}/file", name="documents.file")
def file(
    caller: Reader, services: ServicesDep, customer_id: str, document_id: DocumentId
) -> Response:
    """The file as uploaded, as a download. It is never rendered by the browser from here:
    the sandbox keeps a crafted file from running anything."""
    found = document_file(
        caller.ctx, services.uow(immediate=False), services.storage, customer_id, document_id
    )
    return Response(
        found.data,
        media_type=found.media_type.value,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(found.filename)}",
            "Content-Security-Policy": "sandbox",
        },
    )
