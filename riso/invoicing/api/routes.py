"""The invoicing API: coding a posted invoice without storing it, the number series, and the
lifecycle steps of a stored invoice: check, re-code, the line of a picked position, booking
(with its preview), unbooking, discarding and paying."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from riso.api.deps import Caller, ServicesDep, check_csrf, customer_context
from riso.contracts import Alternative, CodingProposal, InvoiceDocument
from riso.identity import Permission
from riso.invoicing.api.models import (
    BookedOut,
    BookingIn,
    InvoiceOut,
    LastUsedIn,
    LineIn,
    NumberSeriesListOut,
    NumberSeriesOut,
    PaidIn,
    PlacementOut,
    ReasonIn,
)
from riso.invoicing.application import (
    BookInvoice,
    book_invoice,
    check_invoice,
    code_document,
    discard_invoice,
    line_for,
    list_series,
    mark_paid,
    preview_booking,
    recode_invoice,
    set_last_used,
    unbook_invoice,
)
from riso.shared.clock import local_date

router = APIRouter(prefix="/api", dependencies=[Depends(check_csrf)], tags=["invoicing"])

Year = Annotated[int | None, Query(ge=2000, le=2100, description="Default: this year")]


@router.post("/customers/{customer_id}/code", name="coding.code")
def code(
    caller: Annotated[Caller, Depends(customer_context(Permission.INVOICES_PROCESS))],
    services: ServicesDep,
    customer_id: str,
    body: InvoiceDocument,
) -> CodingProposal:
    """The engine's proposal for the invoice, coded with the customer's code lists,
    parameters and conventions for the invoice's booking year, and its supplier memory and
    counters. Nothing is stored. 409 when the customer has no lists or parameters for that
    year."""
    return code_document(
        caller.ctx,
        services.reference_data(),
        services.supplier_state(),
        customer_id,
        body,
        today=local_date(services.clock.now()),
    )


@router.get("/customers/{customer_id}/number-series", name="number_series.list")
def number_series(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
    year: Year = None,
) -> NumberSeriesListOut:
    """The year's number series (plan §7.2): those of the document series list, used or
    not, then any other with a counter; each with its counter, the next number, the numbers
    held and the gaps between them."""
    chosen = year or local_date(services.clock.now()).year
    views = list_series(caller.ctx, services.uow(immediate=False), customer_id, chosen)
    return NumberSeriesListOut(year=chosen, items=[NumberSeriesOut.of(v) for v in views])


@router.put(
    "/customers/{customer_id}/number-series/{series}/{year}", name="number_series.set_last_used"
)
def set_number_series_last_used(
    caller: Annotated[Caller, Depends(customer_context(Permission.CODELISTS_EDIT))],
    services: ServicesDep,
    customer_id: str,
    series: Annotated[str, Path(max_length=16)],
    year: Annotated[int, Path(ge=2000, le=2100)],
    body: LastUsedIn,
) -> NumberSeriesOut:
    """Edits the counter (audited), until it syncs with TOPSET. 422 below a number held;
    404 for a series the year's list does not have."""
    view = set_last_used(caller.ctx, services.uow(), customer_id, series, year, body.last_used)
    return NumberSeriesOut.of(view)


Process = Annotated[Caller, Depends(customer_context(Permission.INVOICES_PROCESS))]
INVOICE = "/customers/{customer_id}/invoices/{invoice_id}"


@router.post(f"{INVOICE}/check", name="invoices.check")
def check(
    caller: Process,
    services: ServicesDep,
    customer_id: str,
    invoice_id: str,
    body: InvoiceDocument,
) -> InvoiceOut:
    """Confirms the invoice's fields (they take the invoice's ID) and codes them: the
    invoice becomes needs_review or ready, or stays checked with the reason the coding could
    not run."""
    view = check_invoice(
        caller.ctx, services.uow(), services.reference_data(), customer_id, invoice_id, body
    )
    return InvoiceOut.of(view)


@router.post(f"{INVOICE}/recode", name="invoices.recode")
def recode(caller: Process, services: ServicesDep, customer_id: str, invoice_id: str) -> InvoiceOut:
    """Codes the checked fields again with today's lists, conventions and memory."""
    view = recode_invoice(
        caller.ctx, services.uow(), services.reference_data(), customer_id, invoice_id
    )
    return InvoiceOut.of(view)


@router.post(f"{INVOICE}/line", name="invoices.line")
def line(
    caller: Process, services: ServicesDep, customer_id: str, invoice_id: str, body: LineIn
) -> Alternative:
    """The whole line (MD, DAL, transfer, texts) a budget position the user picked brings for
    this invoice, for the correction editors. 404 for a position outside the budget."""
    return line_for(
        caller.ctx,
        services.uow(immediate=False),
        services.reference_data(),
        customer_id,
        invoice_id,
        body.budget_key,
    )


def _book(customer_id: str, invoice_id: str, body: BookingIn) -> BookInvoice:
    return BookInvoice(customer_id, invoice_id, body.action, body.coding, body.note)


@router.post(f"{INVOICE}/booking-preview", name="invoices.preview_booking")
def preview(
    caller: Process, services: ServicesDep, customer_id: str, invoice_id: str, body: BookingIn
) -> PlacementOut:
    """The number booking would give and the invoices it would move up, without booking.
    422 and 409 as booking."""
    view = preview_booking(
        caller.ctx,
        services.uow(immediate=False),
        services.reference_data(),
        _book(customer_id, invoice_id, body),
    )
    return PlacementOut.of(view)


@router.post(f"{INVOICE}/book", name="invoices.book")
def book(
    caller: Process, services: ServicesDep, customer_id: str, invoice_id: str, body: BookingIn
) -> BookedOut:
    """Books the proposal (`accepted`, which must be the proposal's coding) or a correction.
    The codes must be in the year's lists (422); the number follows plan §2 decision 61 and
    may move later booked invoices up (409 when an exported or paid one would move). The
    coding becomes the supplier's newest precedent. All in one transaction."""
    result = book_invoice(
        caller.ctx, services.uow(), services.reference_data(), _book(customer_id, invoice_id, body)
    )
    return BookedOut(
        invoice=InvoiceOut.of(result.invoice), placement=PlacementOut.of(result.placement)
    )


@router.post(f"{INVOICE}/unbook", name="invoices.unbook")
def unbook(
    caller: Process, services: ServicesDep, customer_id: str, invoice_id: str, body: ReasonIn
) -> InvoiceOut:
    """Back to checked and coded again (plan §2 decision 62): the precedent goes; the number
    is freed when it is the series' last, else kept for this invoice."""
    view = unbook_invoice(
        caller.ctx,
        services.uow(),
        services.reference_data(),
        customer_id,
        invoice_id,
        reason=body.reason,
    )
    return InvoiceOut.of(view)


@router.post(f"{INVOICE}/discard", name="invoices.discard")
def discard(
    caller: Process, services: ServicesDep, customer_id: str, invoice_id: str, body: ReasonIn
) -> InvoiceOut:
    """Discards an invoice that is not booked. Final."""
    view = discard_invoice(caller.ctx, services.uow(), customer_id, invoice_id, reason=body.reason)
    return InvoiceOut.of(view)


@router.post(f"{INVOICE}/pay", name="invoices.pay")
def pay(
    caller: Process, services: ServicesDep, customer_id: str, invoice_id: str, body: PaidIn
) -> InvoiceOut:
    """Marks a booked or exported invoice paid on the given date. Final."""
    return InvoiceOut.of(
        mark_paid(caller.ctx, services.uow(), customer_id, invoice_id, body.paid_on)
    )
