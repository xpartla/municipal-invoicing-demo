"""Request and response models of the intake API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from riso.contracts import InvoiceDocument
from riso.contracts.base import Amount
from riso.intake.application import DocumentView, EInvoiceDetail, ExtractionView, UploadOutcome
from riso.intake.domain.note import Suggestion


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


class BoxOut(_Out):
    page: int
    box: list[int]
    """Left, top, right, bottom, in the pixels of the page image."""


class SuggestionOut(_Out):
    value: str
    source: Literal["ocr", "counter", "upload"]
    plausible: bool
    reasons: list[str]


class NoteOut(_Out):
    page: int
    box: list[int]
    found: bool
    """Whether ink was found; else the crop is the page's top band."""
    date: list[SuggestionOut]
    number: list[SuggestionOut]


def _suggestions(items: tuple[Suggestion, ...]) -> list[SuggestionOut]:
    return [
        SuggestionOut(
            value=s.value, source=s.source, plausible=s.plausible, reasons=list(s.reasons)
        )
        for s in items
    ]


class ExtractionOut(_Out):
    id: str
    document_id: str
    invoice_id: str
    engine: str
    engine_version: str
    source: Literal["ocr", "text_layer", "einvoice"]
    created_at: datetime
    duration_ms: int
    pages: int
    warnings: list[str]
    confidence: dict[str, float]
    evidence: dict[str, BoxOut]
    note: NoteOut | None
    note_image: bool = Field(description="Whether the note's crop is stored (`documents.note`)")
    number_preview: int | None = Field(
        description="An e-invoice's number has no suggestion: booking places it by its date "
        "of supply (decision 61); this is the number the default series would give now"
    )

    @classmethod
    def of(cls, view: ExtractionView) -> "ExtractionOut":
        note = view.note

        return cls(
            id=view.id,
            document_id=view.document_id,
            invoice_id=view.invoice_id,
            engine=view.engine,
            engine_version=view.engine_version,
            source=view.source,
            created_at=view.created_at,
            duration_ms=view.duration_ms,
            pages=view.pages,
            warnings=list(view.warnings),
            confidence=view.confidence,
            evidence={
                p: BoxOut(page=e.page, box=e.box.to_list()) for p, e in view.evidence.items()
            },
            note=None
            if note is None
            else NoteOut(
                page=note.page,
                box=note.box.to_list(),
                found=note.found,
                date=_suggestions(note.date),
                number=_suggestions(note.number),
            ),
            note_image=view.note_image,
            number_preview=view.number_preview,
        )


class TaxLineOut(_Out):
    category: str = Field(description="UNCL 5305 (`S`, `E`, `O`, …)")
    rate: Amount | None
    taxable: Amount | None
    tax: Amount | None


class EInvoiceOut(_Out):
    """An e-invoice as the viewer renders it (plan §8.4, §8.5): the document as its XML says
    (a credit note's amounts negative), the VAT breakdown, the payable amount, what the XSD
    found, and the raw XML (at most a million characters). A file that could not be read has
    no document, the failure's reason and its raw text."""

    format: Literal["ubl_invoice", "ubl_credit_note", "isdoc"] | None
    family: Literal["ubl", "isdoc"] | None
    version: str | None
    profile: str | None
    attachment: str | None = Field(description="The attachment's name when it came in a PDF")
    document: InvoiceDocument | None
    customer_address: str | None
    taxes: list[TaxLineOut]
    payable: Amount | None
    schema_errors: list[str]
    failure: str | None
    xml: str
    truncated: bool

    @classmethod
    def of(cls, detail: EInvoiceDetail) -> "EInvoiceOut":
        reading = detail.reading
        if reading is None:
            return cls(
                format=None,
                family=None,
                version=None,
                profile=None,
                attachment=None,
                document=None,
                customer_address=None,
                taxes=[],
                payable=None,
                schema_errors=[],
                failure=detail.failure,
                xml=detail.xml,
                truncated=detail.truncated,
            )
        return cls(
            format=reading.format.value,
            family="isdoc" if reading.format.family == "isdoc" else "ubl",
            version=reading.version,
            profile=reading.profile,
            attachment=reading.attachment,
            document=reading.document,
            customer_address=reading.customer_address,
            taxes=[
                TaxLineOut(category=t.category, rate=t.rate, taxable=t.taxable, tax=t.tax)
                for t in reading.taxes
            ],
            payable=reading.payable,
            schema_errors=list(reading.schema_errors),
            failure=None,
            xml=detail.xml,
            truncated=detail.truncated,
        )


class RetryOut(_Out):
    job_id: str
