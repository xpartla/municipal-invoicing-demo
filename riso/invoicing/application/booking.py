"""Booking and what follows it (plan §7.1, §7.2, §2 decisions 61 and 62).

Booking accepts the proposal or a correction of it, in one transaction (the unit of work's
BEGIN IMMEDIATE keeps two bookings apart):

1. the state, and an accepted coding that is not the proposal's, are refused (`Invoice`);
2. the codes must be in the code lists of the booking year (`check_coding`, 422);
3. the number: the handwritten one (or one the user typed or corrected) where it fits, else
   a place by the date of supply; the booked invoices that move up are renumbered, with their
   precedents (`take_number`; 409 when an exported or paid number would have to move);
4. S8: the coding becomes the supplier's newest precedent, linked to the invoice;
5. the invoice is booked and the audit records it.

Any failure rolls all of it back. Unbooking undoes the precedent and frees or reserves the
number, then codes the invoice again. Discarding drops a reservation; paying freezes the
number.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from riso.contracts import Coding
from riso.engine import check_coding, precedent_of
from riso.identity import Permission
from riso.invoicing.application.coding import (
    ReferenceData,
    actor_of,
    code_stored,
    recode_invoice,
)
from riso.invoicing.application.numbering import take_number
from riso.invoicing.application.uow import InvoicingUnitOfWork
from riso.invoicing.application.views import (
    BookingResult,
    InvoiceView,
    ItemResult,
    PlacementView,
)
from riso.invoicing.domain.invoice import BookingAction, Invoice
from riso.invoicing.domain.numbering import HolderKind, Newcomer, NumberSeries, Placement
from riso.reference import ReferenceIndex
from riso.shared.context import RequestContext
from riso.shared.errors import (
    Conflict,
    DomainError,
    FieldError,
    InvalidState,
    NotFound,
    PermissionDenied,
    ValidationFailed,
)
from riso.shared.ids import uuid7_time


@dataclass(frozen=True, slots=True)
class BookInvoice:
    customer_id: str
    invoice_id: str
    action: BookingAction
    coding: Coding
    note: str | None = None


@dataclass(frozen=True, slots=True)
class _Request:
    """Where a booking asks to go in its series."""

    series: str
    year: int
    newcomer: Newcomer
    requested: str | None


def _series(uow: InvoicingUnitOfWork, customer_id: str, code: str, year: int) -> NumberSeries:
    """The stored series, or a transient one with the year's pattern (to read numbers)."""
    stored = uow.number_series.find(customer_id, code, year)
    if stored is not None:
        return stored
    pattern = uow.series_patterns.patterns(customer_id, year).get(code)
    if pattern is None:
        raise ValidationFailed.on(
            "coding.document.series",
            f"the {year} document series list has no series {code}",
            "unknown_series",
        )
    return NumberSeries.new("transient", customer_id, code, year, pattern, uow.clock.now())


def _request(uow: InvoicingUnitOfWork, invoice: Invoice, coding: Coding) -> _Request:
    """The series, year and place the booking asks for. A number counts as asked for when it
    was handwritten (and checked) or the user typed another than the proposal's."""
    assert invoice.fields is not None and invoice.proposal is not None
    document = coding.document
    if document.booking_date is None:
        raise ValidationFailed.on(
            "coding.document.booking_date", "the booking date is missing", "required"
        )
    supplied = invoice.supply_date
    if supplied is None:
        raise ValidationFailed.on(
            "fields.invoice.delivery_date",
            "the date of supply (or the issue date) is missing",
            "supply_date_missing",
        )
    year = document.booking_date.year
    series = _series(uow, invoice.customer_id, document.series, year)
    typed = document.number
    asked = invoice.fields.handwritten.number is not None or (
        typed is not None and typed != invoice.proposal.document.number
    )
    sequence = None
    if asked:
        sequence = series.sequence_of(typed) if typed else None
        if sequence is None:
            raise ValidationFailed.on(
                "coding.document.number",
                f"{typed} is not a number of {series.pattern} in {year}",
                "number_pattern",
            )
    newcomer = Newcomer(invoice.id, supplied, arrival(invoice), sequence)
    return _Request(document.series, year, newcomer, typed if asked else None)


def arrival(invoice: Invoice) -> datetime:
    """When the invoice came in, for decision 61's order: the time in its UUIDv7 ID, which
    the ID generator never lets go back, even when the wall clock is set back between two
    uploads (P2-M5-T15); its upload time for an ID that is not a UUIDv7."""
    try:
        return uuid7_time(invoice.id)
    except ValueError:
        return invoice.uploaded_at


def _check_codes(
    ctx: RequestContext, reference: ReferenceData, customer_id: str, year: int, coding: Coding
) -> None:
    bundle = reference.bundle(ctx, customer_id, year)
    errors = check_coding(coding, ReferenceIndex(bundle)).errors
    if errors:
        raise ValidationFailed(
            "the coding uses codes outside the code lists",
            [FieldError("coding", error, "not_in_lists") for error in errors],
        )


def _prepare(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    reference: ReferenceData,
    cmd: BookInvoice,
) -> tuple[Invoice, _Request]:
    invoice = uow.invoices.get(cmd.customer_id, cmd.invoice_id)
    invoice.ensure_bookable(cmd.coding, cmd.action)
    request = _request(uow, invoice, cmd.coding)
    _check_codes(ctx, reference, cmd.customer_id, request.year, cmd.coding)
    return invoice, request


def preview_booking(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    reference: ReferenceData,
    cmd: BookInvoice,
) -> PlacementView:
    """What booking would do to the numbers, for the confirmation: the number it gets and
    the invoices it moves up. Raises as booking would (409 for a frozen number)."""
    ctx.require(Permission.INVOICES_PROCESS, cmd.customer_id)
    with uow:
        _, request = _prepare(ctx, uow, reference, cmd)
        series = _series(uow, cmd.customer_id, request.series, request.year)
        placement = series.preview(request.newcomer, requested=request.requested)
    return PlacementView.of(placement)


def book_invoice(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    reference: ReferenceData,
    cmd: BookInvoice,
) -> BookingResult:
    ctx.require(Permission.INVOICES_PROCESS, cmd.customer_id)
    actor = actor_of(ctx)
    with uow:
        at = uow.clock.now()
        invoice, request = _prepare(ctx, uow, reference, cmd)
        placement = take_number(
            uow,
            cmd.customer_id,
            request.series,
            request.year,
            request.newcomer,
            requested=request.requested,
        )
        _renumber(ctx, uow, invoice, placement, at)
        invoice.book(cmd.coding, cmd.action, placement.number, at, actor, note=cmd.note)
        assert invoice.booking is not None and invoice.proposal is not None
        supplier = invoice.proposal.supplier
        if supplier.ico is not None:
            uow.supplier_memory.add_precedent(
                cmd.customer_id,
                supplier.ico,
                supplier.name or supplier.ico,
                precedent_of(invoice.booking.coding, invoice.proposal.invoice.vs),
                invoice_id=invoice.id,
            )
        uow.invoices.save(invoice)
        uow.audit.record(
            ctx,
            "invoice.booked",
            target_type="invoice",
            target_id=invoice.id,
            customer_id=cmd.customer_id,
            details={
                "number": placement.number,
                "action": cmd.action,
                "requested": request.requested,
                "moved": placement.moved,
                "renumbered": [s.invoice_id for s in placement.shifts if s.invoice_id],
            },
        )
        uow.commit()
    return BookingResult(InvoiceView.of(invoice), PlacementView.of(placement))


def _renumber(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    because_of: Invoice,
    placement: Placement,
    at: datetime,
) -> None:
    """The booked invoices the placement moved up get their new numbers, and so do their
    precedents. A moved reservation needs nothing more."""
    actor = actor_of(ctx)
    for shift in placement.shifts:
        if shift.invoice_id is None or shift.kind is not HolderKind.BOOKED:
            continue
        other = uow.invoices.get(because_of.customer_id, shift.invoice_id)
        other.renumber(shift.new, at, actor, because_of=because_of.id)
        uow.invoices.save(other)
        uow.supplier_memory.renumber(because_of.customer_id, other.id, shift.new)
        uow.audit.record(
            ctx,
            "invoice.renumbered",
            target_type="invoice",
            target_id=other.id,
            customer_id=because_of.customer_id,
            details={"from": shift.old, "to": shift.new, "by": because_of.id},
        )


def unbook_invoice(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    reference: ReferenceData,
    customer_id: str,
    invoice_id: str,
    *,
    reason: str | None = None,
) -> InvoiceView:
    """Back to checked (decision 62): the booking's precedent goes; the number is freed when
    it is the series' last, else kept for the invoice; then the invoice is coded again."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    actor = actor_of(ctx)
    with uow:
        at = uow.clock.now()
        invoice = uow.invoices.get(customer_id, invoice_id)
        booking = invoice.unbook(at, actor, reason=reason)
        released = []
        for series in uow.number_series.holding(customer_id, invoice_id):
            released.append(series.release(invoice_id, at).value)
            uow.number_series.save(series)
        removed = uow.supplier_memory.remove_precedents_of(customer_id, invoice_id)
        code_stored(ctx, uow, reference, invoice, actor)
        uow.invoices.save(invoice)
        uow.audit.record(
            ctx,
            "invoice.unbooked",
            target_type="invoice",
            target_id=invoice_id,
            customer_id=customer_id,
            details={"number": booking.number, "number_kept": released, "precedents": removed},
        )
        uow.commit()
    return InvoiceView.of(invoice)


def discard_invoice(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    customer_id: str,
    invoice_id: str,
    *,
    reason: str | None = None,
) -> InvoiceView:
    """An invoice that will not be booked (any state before booking); a number it kept from
    an unbooking is let go."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    with uow:
        at = uow.clock.now()
        invoice = uow.invoices.get(customer_id, invoice_id)
        invoice.discard(at, actor_of(ctx), reason=reason)
        for series in uow.number_series.holding(customer_id, invoice_id):
            if series.drop_reservation(invoice_id, at):
                uow.number_series.save(series)
        uow.invoices.save(invoice)
        uow.audit.record(
            ctx,
            "invoice.discarded",
            target_type="invoice",
            target_id=invoice_id,
            customer_id=customer_id,
        )
        uow.commit()
    return InvoiceView.of(invoice)


def mark_paid(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    customer_id: str,
    invoice_id: str,
    paid_on: date,
) -> InvoiceView:
    """The user's payment date (decision 15). The invoice's number never moves again."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    with uow:
        at = uow.clock.now()
        invoice = uow.invoices.get(customer_id, invoice_id)
        invoice.mark_paid(paid_on, at, actor_of(ctx))
        for series in uow.number_series.holding(customer_id, invoice_id):
            if series.freeze(invoice_id, at):
                uow.number_series.save(series)
        uow.invoices.save(invoice)
        uow.audit.record(
            ctx,
            "invoice.paid",
            target_type="invoice",
            target_id=invoice_id,
            customer_id=customer_id,
            details={"paid_on": paid_on.isoformat()},
        )
        uow.commit()
    return InvoiceView.of(invoice)


_CODES: tuple[tuple[type[DomainError], str], ...] = (
    (NotFound, "not_found"),
    (PermissionDenied, "permission_denied"),
    (ValidationFailed, "validation_failed"),
    (InvalidState, "invalid_state"),
    (Conflict, "conflict"),
)


def each(invoice_ids: list[str], action: Callable[[str], object]) -> list[ItemResult]:
    """Runs a single-invoice use case for each invoice in its own transaction, so one
    invoice's failure is reported and the others go on."""
    results = []
    for invoice_id in dict.fromkeys(invoice_ids):
        try:
            action(invoice_id)
        except DomainError as exc:
            code = exc.code or next((c for kind, c in _CODES if isinstance(exc, kind)), "error")
            results.append(ItemResult(invoice_id, False, code, exc.message))
        else:
            results.append(ItemResult(invoice_id, True))
    return results


def mark_paid_many(
    ctx: RequestContext,
    uow: Callable[[], InvoicingUnitOfWork],
    customer_id: str,
    invoice_ids: list[str],
    paid_on: date,
) -> list[ItemResult]:
    """Marks several invoices paid on one date; each succeeds or fails on its own."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    return each(invoice_ids, lambda i: mark_paid(ctx, uow(), customer_id, i, paid_on))


def recode_many(
    ctx: RequestContext,
    uow: Callable[[], InvoicingUnitOfWork],
    reference: ReferenceData,
    customer_id: str,
    invoice_ids: list[str],
) -> list[ItemResult]:
    """Codes several invoices again; each succeeds or fails on its own."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    return each(invoice_ids, lambda i: recode_invoice(ctx, uow(), reference, customer_id, i))


def discard_many(
    ctx: RequestContext,
    uow: Callable[[], InvoicingUnitOfWork],
    customer_id: str,
    invoice_ids: list[str],
    *,
    reason: str | None = None,
) -> list[ItemResult]:
    """Discards several invoices; each succeeds or fails on its own."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    return each(invoice_ids, lambda i: discard_invoice(ctx, uow(), customer_id, i, reason=reason))
