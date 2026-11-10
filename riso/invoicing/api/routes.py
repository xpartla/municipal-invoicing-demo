"""The invoicing API: coding a posted invoice without storing it, the number series, and the
lifecycle steps of a stored invoice: check, re-code, the line of a picked position, booking
(with its preview), unbooking, discarding and paying."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from riso.api.deps import Caller, ServicesDep, check_csrf, customer_context
from riso.contracts import Alternative, CodingProposal, InvoiceDocument
from riso.identity import Permission
from riso.invoicing.api.models import (
    BookedOut,
    BookingIn,
    BulkDiscardIn,
    BulkIn,
    BulkOut,
    BulkPayIn,
    ChannelName,
    HistoryOut,
    InvoiceOut,
    InvoicePageOut,
    InvoiceRowOut,
    LastUsedIn,
    LineIn,
    NumberSeriesListOut,
    NumberSeriesOut,
    PaidIn,
    PlacementOut,
    ReasonIn,
    State,
    SupplierOut,
)
from riso.invoicing.application import (
    BookInvoice,
    InvoiceFilter,
    Sort,
    book_invoice,
    check_invoice,
    code_document,
    discard_invoice,
    discard_many,
    enter_after_failure,
    enter_invoice,
    find_suppliers,
    get_invoice,
    invoice_history,
    line_for,
    list_invoices,
    list_series,
    mark_paid,
    mark_paid_many,
    preview_booking,
    recode_invoice,
    recode_many,
    set_last_used,
    unbook_invoice,
)
from riso.shared.clock import local_date
from riso.shared.errors import ValidationFailed

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


@router.post("/customers/{customer_id}/invoices", name="invoices.create", status_code=201)
def create(
    caller: Process, services: ServicesDep, customer_id: str, body: InvoiceDocument
) -> InvoiceOut:
    """Manual entry (plan §8.5): an invoice from typed fields, checked and coded at once.
    The fields' `id` is replaced by the new invoice's."""
    view = enter_invoice(caller.ctx, services.uow(), services.reference_data(), customer_id, body)
    return InvoiceOut.of(view)


@router.post(INVOICE + "/manual", name="invoices.enter_manually")
def enter_manually(
    caller: Process,
    services: ServicesDep,
    customer_id: str,
    invoice_id: str,
    body: InvoiceDocument,
) -> InvoiceOut:
    """Manual entry of an uploaded invoice whose file could not be read (plan §7.1): the
    typed fields, checked and coded at once; the invoice keeps its document."""
    view = enter_after_failure(
        caller.ctx, services.uow(), services.reference_data(), customer_id, invoice_id, body
    )
    return InvoiceOut.of(view)


Read = Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))]
INVOICES = "/customers/{customer_id}/invoices"
Day = Annotated[date | None, Query()]


@router.get(INVOICES, name="invoices.list")
def invoices(  # noqa: PLR0913 - one parameter per filter of plan §10.3
    caller: Read,
    services: ServicesDep,
    customer_id: str,
    q: Annotated[str | None, Query(max_length=200, description="Supplier, numbers, VS")] = None,
    supplier_ico: Annotated[str | None, Query(max_length=8)] = None,
    state: Annotated[list[State] | None, Query()] = None,
    series: Annotated[list[str] | None, Query()] = None,
    channel: Annotated[list[ChannelName] | None, Query()] = None,
    needs_review: bool | None = None,
    uploaded_by: str | None = None,
    issue_from: Day = None,
    issue_to: Day = None,
    due_from: Day = None,
    due_to: Day = None,
    booking_from: Day = None,
    booking_to: Day = None,
    uploaded_from: Day = None,
    uploaded_to: Day = None,
    exported_from: Day = None,
    exported_to: Day = None,
    paid_from: Day = None,
    paid_to: Day = None,
    amount_min: Annotated[Decimal | None, Query()] = None,
    amount_max: Annotated[Decimal | None, Query()] = None,
    budget: Annotated[str | None, Query(max_length=32, description="Key or EK prefix")] = None,
    md: Annotated[str | None, Query(max_length=16, description="Prefix")] = None,
    dal: Annotated[str | None, Query(max_length=16, description="Prefix")] = None,
    sort: Annotated[str | None, Query(description="e.g. -booking_date")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> InvoicePageOut:
    """The invoice table (plan §10.3): every filter, sorting by a column (`-` for
    descending; default `-uploaded_at`) and paging. Text filters ignore case and diacritics;
    dates are inclusive days."""
    try:
        order = Sort.parse(sort)
    except ValueError as exc:
        raise ValidationFailed.on("sort", str(exc)) from exc
    criteria = InvoiceFilter(
        text=q,
        supplier_ico=supplier_ico,
        states=state or (),
        series=series or (),
        channels=channel or (),
        needs_review=needs_review,
        uploaded_by=uploaded_by,
        issue_from=issue_from,
        issue_to=issue_to,
        due_from=due_from,
        due_to=due_to,
        booking_from=booking_from,
        booking_to=booking_to,
        uploaded_from=uploaded_from,
        uploaded_to=uploaded_to,
        exported_from=exported_from,
        exported_to=exported_to,
        paid_from=paid_from,
        paid_to=paid_to,
        amount_min=amount_min,
        amount_max=amount_max,
        budget=budget,
        md=md,
        dal=dal,
    )
    found = list_invoices(
        caller.ctx,
        services.uow(immediate=False),
        customer_id,
        criteria,
        order,
        page=page,
        size=size,
    )
    return InvoicePageOut(items=[InvoiceRowOut.of(r) for r in found.items], total=found.total)


@router.get(f"{INVOICES}/suppliers", name="invoices.suppliers")
def suppliers(
    caller: Read,
    services: ServicesDep,
    customer_id: str,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[SupplierOut]:
    """The suppliers of the customer's invoices whose name or IČO matches, most invoices
    first, for the supplier filter."""
    found = find_suppliers(caller.ctx, services.uow(immediate=False), customer_id, q)
    return [SupplierOut(ico=s.ico, name=s.name, invoices=s.invoices) for s in found]


@router.post(f"{INVOICES}/bulk/pay", name="invoices.bulk_pay")
def bulk_pay(caller: Process, services: ServicesDep, customer_id: str, body: BulkPayIn) -> BulkOut:
    """Marks several invoices paid on one date; each is reported on its own."""
    results = mark_paid_many(caller.ctx, services.uow, customer_id, body.invoice_ids, body.paid_on)
    return BulkOut.of(results)


@router.post(f"{INVOICES}/bulk/recode", name="invoices.bulk_recode")
def bulk_recode(caller: Process, services: ServicesDep, customer_id: str, body: BulkIn) -> BulkOut:
    """Codes several invoices again; each is reported on its own."""
    results = recode_many(
        caller.ctx, services.uow, services.reference_data(), customer_id, body.invoice_ids
    )
    return BulkOut.of(results)


@router.post(f"{INVOICES}/bulk/discard", name="invoices.bulk_discard")
def bulk_discard(
    caller: Process, services: ServicesDep, customer_id: str, body: BulkDiscardIn
) -> BulkOut:
    """Discards several invoices that are not booked; each is reported on its own."""
    results = discard_many(
        caller.ctx, services.uow, customer_id, body.invoice_ids, reason=body.reason
    )
    return BulkOut.of(results)


@router.get(INVOICE, name="invoices.get")
def invoice(caller: Read, services: ServicesDep, customer_id: str, invoice_id: str) -> InvoiceOut:
    """One invoice: its fields, proposal, booking, timestamps and what its state allows."""
    return InvoiceOut.of(
        get_invoice(caller.ctx, services.uow(immediate=False), customer_id, invoice_id)
    )


@router.get(f"{INVOICE}/history", name="invoices.history")
def history(caller: Read, services: ServicesDep, customer_id: str, invoice_id: str) -> HistoryOut:
    """The invoice's history, oldest first: every step with who took it (plan §10.4)."""
    return HistoryOut.of(
        invoice_history(caller.ctx, services.uow(immediate=False), customer_id, invoice_id)
    )


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
