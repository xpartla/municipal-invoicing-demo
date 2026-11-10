"""What the intake use cases return."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from riso.intake.domain import Document, MediaType


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
