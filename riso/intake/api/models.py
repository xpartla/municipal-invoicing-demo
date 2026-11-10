"""Request and response models of the intake API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from riso.intake.application import DocumentView, UploadOutcome


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UploadItemOut(_Out):
    """One uploaded file: `accepted` with its document, invoice and extraction job, or
    `rejected` with the reason (`file_empty`, `file_too_large`, `file_type`, `too_many_pages`,
    `duplicate`); a duplicate links the invoice the same file became."""

    filename: str
    status: Literal["accepted", "rejected"]
    document_id: str | None
    invoice_id: str | None
    job_id: str | None
    reason: str | None
    message: str | None
    duplicate_of: str | None

    @classmethod
    def of(cls, outcome: UploadOutcome) -> "UploadItemOut":
        return cls(
            filename=outcome.filename,
            status=outcome.status,
            document_id=outcome.document_id,
            invoice_id=outcome.invoice_id,
            job_id=outcome.job_id,
            reason=outcome.reason,
            message=outcome.message,
            duplicate_of=outcome.duplicate_of,
        )


class UploadOut(_Out):
    items: list[UploadItemOut]
    accepted: int
    rejected: int


class DocumentOut(_Out):
    id: str
    filename: str
    media_type: str
    size: int
    pages: int | None
    uploaded_at: datetime
    uploaded_by: str | None
    invoice_id: str | None

    @classmethod
    def of(cls, view: DocumentView) -> "DocumentOut":
        return cls(
            id=view.id,
            filename=view.filename,
            media_type=view.media_type.value,
            size=view.size,
            pages=view.pages,
            uploaded_at=view.uploaded_at,
            uploaded_by=view.uploaded_by,
            invoice_id=view.invoice_id,
        )
