"""Request and response models of the invoicing API."""

from dataclasses import asdict
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from riso.contracts import Coding, CodingProposal, InvoiceDocument
from riso.contracts.base import BudgetKey
from riso.invoicing.application import InvoiceView, PlacementView, SeriesView


class UsedNumberOut(BaseModel):
    number: str
    sequence: int
    kind: Literal["booked", "reserved", "external"] = Field(
        description="A booked invoice's; one kept for an unbooked invoice; or used outside riso"
    )
    invoice_id: str | None
    frozen: bool = Field(description="Never moves: exported, paid or used outside riso")


class NumberSeriesOut(BaseModel):
    series: str
    year: int
    pattern: str
    last_used: int = Field(description="The counter: the last sequence used")
    last_used_number: str | None
    next_number: str = Field(description="What the counter gives next")
    used: list[UsedNumberOut] = Field(description="The numbers held, lowest first")
    gaps: list[str] = Field(description="Free numbers between the lowest and the highest held")
    stored: bool = Field(description="False for a series of the year's list never used yet")

    @classmethod
    def of(cls, view: SeriesView) -> "NumberSeriesOut":
        return cls(
            series=view.series,
            year=view.year,
            pattern=view.pattern,
            last_used=view.last_used,
            last_used_number=view.last_used_number,
            next_number=view.next_number,
            used=[UsedNumberOut.model_validate(asdict(u)) for u in view.used],
            gaps=list(view.gaps),
            stored=view.stored,
        )


class NumberSeriesListOut(BaseModel):
    year: int
    items: list[NumberSeriesOut]


class LastUsedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_used: int = Field(ge=0, description="The new counter: the last sequence used")


class BasisOut(BaseModel):
    """What the proposal was coded with (plan §6.2, decision 56)."""

    year: int
    bundle_id: str
    version_ids: list[str]
    conventions_revision: int | None


class BookingOut(BaseModel):
    coding: Coding
    action: Literal["accepted", "corrected"]
    at: datetime
    by: str | None
    note: str | None


Action = Literal["check", "recode", "book", "unbook", "export", "pay", "discard"]


class InvoiceOut(BaseModel):
    id: str
    customer_id: str
    channel: Literal["scan", "digital_pdf", "einvoice", "manual", "dataset"]
    state: Literal[
        "uploaded",
        "extracting",
        "extraction_failed",
        "extracted",
        "checked",
        "needs_review",
        "ready",
        "booked",
        "exported",
        "paid",
        "discarded",
        "duplicate",
    ]
    source_ref: str | None = Field(description="The dataset case, or the uploaded file's name")
    document_id: str | None
    fields: InvoiceDocument | None = Field(description="The fields, as extracted or checked")
    proposal: CodingProposal | None
    basis: BasisOut | None
    coding_error: str | None = Field(description="Why the last coding could not run")
    needs_review: bool
    booking: BookingOut | None
    number: str | None = Field(description="The booked document number")
    paid_on: date | None
    uploaded_at: datetime
    uploaded_by: str | None
    checked_at: datetime | None
    coded_at: datetime | None
    booked_at: datetime | None
    exported_at: datetime | None
    paid_at: datetime | None
    discarded_at: datetime | None
    discard_reason: str | None
    extraction_error: str | None
    actions: list[Action] = Field(description="What the invoice's state allows")

    @classmethod
    def of(cls, view: InvoiceView) -> "InvoiceOut":
        return cls.model_validate(
            {
                **{name: getattr(view, name) for name in InvoiceView.__slots__},
                "basis": asdict(view.basis) if view.basis else None,
                "booking": asdict(view.booking) if view.booking else None,
                "actions": list(view.actions),
            }
        )


class ShiftOut(BaseModel):
    invoice_id: str | None = Field(description="None for a number kept for an unbooked invoice")
    old: str
    new: str


class PlacementOut(BaseModel):
    """The number a booking gets, or would get, and the invoices it moves up (decision 61)."""

    number: str
    requested: str | None = Field(description="The handwritten or typed number asked for")
    moved: bool = Field(description="An invoice supplied earlier holds the number asked for")
    shifts: list[ShiftOut]

    @classmethod
    def of(cls, view: PlacementView) -> "PlacementOut":
        return cls.model_validate(asdict(view))


class BookingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["accepted", "corrected"]
    coding: Coding = Field(description="The proposal's coding, or the corrected one")
    note: str | None = Field(default=None, max_length=500)


class BookedOut(BaseModel):
    invoice: InvoiceOut
    placement: PlacementOut


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


class PaidIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paid_on: date


class LineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_key: BudgetKey
