"""The views (DTOs) the invoicing use cases return."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from riso.contracts import Coding, CodingProposal, InvoiceDocument
from riso.invoicing.domain.invoice import CodingBasis, EventKind, Invoice, InvoiceEvent
from riso.invoicing.domain.numbering import Placement

ACTIONS: dict[EventKind, str] = {
    EventKind.CHECKED: "check",
    EventKind.CODED: "recode",
    EventKind.BOOKED: "book",
    EventKind.UNBOOKED: "unbook",
    EventKind.EXPORTED: "export",
    EventKind.PAID: "pay",
    EventKind.DISCARDED: "discard",
}
"""What a user can do to an invoice, by the lifecycle step it takes."""


@dataclass(frozen=True, slots=True)
class BookingView:
    coding: Coding
    action: str
    at: datetime
    by: str | None
    note: str | None


@dataclass(frozen=True, slots=True)
class InvoiceView:
    id: str
    customer_id: str
    channel: str
    state: str
    source_ref: str | None
    document_id: str | None
    fields: InvoiceDocument | None
    proposal: CodingProposal | None
    basis: CodingBasis | None
    coding_error: str | None
    needs_review: bool
    booking: BookingView | None
    number: str | None
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
    actions: tuple[str, ...]
    """What the invoice's state allows (`book`, `pay` …); the caller's permissions apply too."""

    @classmethod
    def of(cls, invoice: Invoice) -> "InvoiceView":
        booking = invoice.booking
        return cls(
            id=invoice.id,
            customer_id=invoice.customer_id,
            channel=invoice.channel.value,
            state=invoice.state.value,
            source_ref=invoice.source_ref,
            document_id=invoice.document_id,
            fields=invoice.fields,
            proposal=invoice.proposal,
            basis=invoice.basis,
            coding_error=invoice.coding_error,
            needs_review=invoice.needs_review,
            booking=BookingView(
                booking.coding, booking.action, booking.at, booking.by, booking.note
            )
            if booking
            else None,
            number=invoice.number,
            paid_on=invoice.paid_on,
            uploaded_at=invoice.uploaded_at,
            uploaded_by=invoice.uploaded_by,
            checked_at=invoice.checked_at,
            coded_at=invoice.coded_at,
            booked_at=invoice.booked_at,
            exported_at=invoice.exported_at,
            paid_at=invoice.paid_at,
            discarded_at=invoice.discarded_at,
            discard_reason=invoice.discard_reason,
            extraction_error=invoice.extraction_error,
            actions=tuple(
                name
                for kind, name in ACTIONS.items()
                if invoice.can(kind) and (kind is not EventKind.CHECKED or invoice.fields)
            ),
        )


@dataclass(frozen=True, slots=True)
class HistoryEntryView:
    kind: str
    at: datetime
    actor_id: str | None
    real_actor_id: str | None
    from_state: str | None
    to_state: str
    details: dict[str, Any]

    @classmethod
    def of(cls, event: InvoiceEvent) -> "HistoryEntryView":
        return cls(
            event.kind.value,
            event.at,
            event.actor_id,
            event.real_actor_id,
            event.from_state.value if event.from_state else None,
            event.to_state.value,
            dict(event.details),
        )


@dataclass(frozen=True, slots=True)
class ShiftView:
    invoice_id: str | None
    old: str
    new: str


@dataclass(frozen=True, slots=True)
class PlacementView:
    """The number a booking gets (or would get) and the invoices it moves up."""

    number: str
    requested: str | None
    moved: bool
    """It did not get the number it asked for: another invoice supplied earlier holds it."""
    shifts: tuple[ShiftView, ...]

    @classmethod
    def of(cls, placement: Placement) -> "PlacementView":
        return cls(
            placement.number,
            placement.requested,
            placement.moved,
            tuple(ShiftView(s.invoice_id, s.old, s.new) for s in placement.shifts),
        )


@dataclass(frozen=True, slots=True)
class BookingResult:
    invoice: InvoiceView
    placement: PlacementView


@dataclass(frozen=True, slots=True)
class ItemResult:
    """One invoice's outcome in a bulk action."""

    invoice_id: str
    ok: bool
    code: str | None = None
    message: str | None = None
