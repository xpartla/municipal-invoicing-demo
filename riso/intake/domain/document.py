"""The `Document` aggregate (plan §7.3, §8.2, §12, decision 18): one uploaded file of a
customer, kept content-addressed in its storage.

What a file is comes from its first bytes, never from its name: PDF, JPEG, PNG or TIFF (XML
joins with the e-invoices in P2-M6). A file is at most 20 MB and 5 pages. The same content
(its SHA-256) is held once per customer: a second upload is refused with the invoice the
first one became.
"""

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from riso.shared.errors import ValidationFailed
from riso.shared.events import DomainEvent

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 5
MAX_FILENAME = 200
SNIFF_BYTES = 1024
"""How far into a file its signature is looked for: a PDF may start after some junk."""


class MediaType(StrEnum):
    PDF = "application/pdf"
    JPEG = "image/jpeg"
    PNG = "image/png"
    TIFF = "image/tiff"

    @property
    def extension(self) -> str:
        return _EXTENSIONS[self]

    @property
    def is_image(self) -> bool:
        return self is not MediaType.PDF


_EXTENSIONS = {
    MediaType.PDF: "pdf",
    MediaType.JPEG: "jpg",
    MediaType.PNG: "png",
    MediaType.TIFF: "tif",
}

_SIGNATURES = (
    (b"\xff\xd8\xff", MediaType.JPEG),
    (b"\x89PNG\r\n\x1a\n", MediaType.PNG),
    (b"II*\x00", MediaType.TIFF),
    (b"MM\x00*", MediaType.TIFF),
)


def sniff(data: bytes) -> MediaType | None:
    """The file's type from its signature: images at the start, a PDF's `%PDF-` within the
    first kilobyte (readers accept leading junk, so the check must too). None for anything
    else, whatever its name says."""
    for signature, media_type in _SIGNATURES:
        if data.startswith(signature):
            return media_type
    if b"%PDF-" in data[:SNIFF_BYTES]:
        return MediaType.PDF
    return None


def safe_filename(name: str | None) -> str:
    """The name as uploaded, made harmless for display and for a download header: the last
    path part, without control characters, normalised, at most 200 characters."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    text = "".join(
        c for c in unicodedata.normalize("NFC", base) if unicodedata.category(c)[0] != "C"
    )
    text = text.strip().strip(".")[:MAX_FILENAME].strip()
    return text or "dokument"


def check_upload(size: int, media_type: MediaType | None, pages: int | None) -> MediaType:
    """Refuses a file the intake does not take, with the reason as the error's code:
    `file_empty`, `file_too_large`, `file_type` or `too_many_pages`. A file whose pages cannot
    be counted (a damaged PDF) is taken; its extraction says what is wrong with it."""
    if size == 0:
        raise ValidationFailed.on("file", "the file is empty", "file_empty")
    if size > MAX_BYTES:
        raise ValidationFailed.on(
            "file", f"larger than {MAX_BYTES // (1024 * 1024)} MB", "file_too_large"
        )
    if media_type is None:
        raise ValidationFailed.on("file", "not a PDF, JPEG, PNG or TIFF file", "file_type")
    if pages is not None and pages > MAX_PAGES:
        raise ValidationFailed.on(
            "file", f"{pages} pages; at most {MAX_PAGES} are read", "too_many_pages"
        )
    return media_type


@dataclass(frozen=True, slots=True)
class DocumentUploaded(DomainEvent):
    document_id: str
    customer_id: str
    media_type: MediaType
    at: datetime


@dataclass(slots=True)
class Document:
    id: str
    customer_id: str
    sha256: str
    filename: str
    media_type: MediaType
    size: int
    pages: int | None
    """None when they could not be counted (the file is damaged)."""
    storage_key: str
    uploaded_at: datetime
    uploaded_by: str | None
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def uploaded(
        cls,
        document_id: str,
        customer_id: str,
        *,
        sha256: str,
        filename: str,
        media_type: MediaType,
        size: int,
        pages: int | None,
        storage_key: str,
        at: datetime,
        actor_id: str | None,
    ) -> "Document":
        check_upload(size, media_type, pages)
        if len(sha256) != 64:
            raise ValidationFailed.on("sha256", "not a SHA-256 digest")
        document = cls(
            id=document_id,
            customer_id=customer_id,
            sha256=sha256,
            filename=safe_filename(filename),
            media_type=media_type,
            size=size,
            pages=pages,
            storage_key=storage_key,
            uploaded_at=at,
            uploaded_by=actor_id,
        )
        document.events.append(DocumentUploaded(document_id, customer_id, media_type, at))
        return document
