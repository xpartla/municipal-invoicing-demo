"""The `Extraction` aggregate (plan §4.7, §8.2 step 6, §8.3): what one reading of a document
produced. It keeps the engine and its version (so quality can be compared per engine), the
`InvoiceDocument` with its confidences, where each field was read, the warnings, the note's
suggestions, the stored page images, layout and crop, and how long it took. A document read
again (a retry) gets a new extraction; the newest is the one the check step shows.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from riso.contracts import InvoiceDocument
from riso.intake.domain.extract import Evidence
from riso.intake.domain.note import NoteSuggestions
from riso.shared.events import DomainEvent

Source = Literal["ocr", "text_layer", "einvoice"]


@dataclass(frozen=True, slots=True)
class DocumentExtracted(DomainEvent):
    extraction_id: str
    document_id: str
    invoice_id: str
    customer_id: str
    at: datetime


@dataclass(slots=True)
class Extraction:
    id: str
    customer_id: str
    document_id: str
    invoice_id: str
    engine: str
    engine_version: str
    source: Source
    document: InvoiceDocument
    evidence: Mapping[str, Evidence]
    warnings: tuple[str, ...]
    note: NoteSuggestions | None
    page_keys: tuple[str, ...]
    """The normalised pages' images in storage, in page order: what the check step shows."""
    layout_key: str | None
    """The words with their boxes in storage; None for an e-invoice, which has none."""
    note_key: str | None
    """The note's crop in storage."""
    duration_ms: int
    created_at: datetime
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def recorded(
        cls,
        extraction_id: str,
        *,
        customer_id: str,
        document_id: str,
        invoice_id: str,
        engine: str,
        engine_version: str,
        source: Source,
        document: InvoiceDocument,
        evidence: Mapping[str, Evidence],
        warnings: tuple[str, ...],
        note: NoteSuggestions | None,
        page_keys: tuple[str, ...],
        layout_key: str | None,
        note_key: str | None,
        duration_ms: int,
        at: datetime,
    ) -> "Extraction":
        if document.handwritten.date is not None or document.handwritten.number is not None:
            raise ValueError("an extraction never fills the handwritten fields (plan §8.1)")
        extraction = cls(
            id=extraction_id,
            customer_id=customer_id,
            document_id=document_id,
            invoice_id=invoice_id,
            engine=engine,
            engine_version=engine_version,
            source=source,
            document=document,
            evidence=dict(evidence),
            warnings=warnings,
            note=note,
            page_keys=page_keys,
            layout_key=layout_key,
            note_key=note_key,
            duration_ms=duration_ms,
            created_at=at,
        )
        extraction.events.append(
            DocumentExtracted(extraction_id, document_id, invoice_id, customer_id, at)
        )
        return extraction
