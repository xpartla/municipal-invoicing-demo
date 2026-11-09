"""Reading invoices (plan §10.3, §10.4): the table with its filters, sorting and paging; one
invoice; its history with the names of the people in it; the suppliers for the supplier
filter. Read only; `customer.read`."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal, Protocol, cast, get_args

from riso.identity import Permission
from riso.invoicing.application.uow import InvoicingUnitOfWork
from riso.invoicing.application.views import HistoryEntryView, InvoiceView
from riso.shared.clock import BRATISLAVA
from riso.shared.context import RequestContext

SortKey = Literal[
    "state",
    "document_number",
    "booking_date",
    "supplier_name",
    "supplier_ico",
    "invoice_number",
    "variable_symbol",
    "issue_date",
    "due_date",
    "supply_date",
    "gross",
    "uploaded_at",
    "exported_at",
    "paid_on",
]
SORT_KEYS: tuple[str, ...] = get_args(SortKey)
MAX_SIZE = 200


@dataclass(frozen=True, slots=True)
class Sort:
    key: SortKey = "uploaded_at"
    descending: bool = True

    @classmethod
    def parse(cls, text: str | None) -> "Sort":
        """`-booking_date` sorts by booking date, newest first; `supplier_name` A to Z."""
        if not text:
            return cls()
        key = text.removeprefix("-")
        if key not in SORT_KEYS:
            raise ValueError(f"cannot sort by {key}")
        return cls(cast(SortKey, key), text.startswith("-"))


@dataclass(frozen=True, slots=True)
class InvoiceFilter:
    """The table's filters (plan §10.3). Dates are days; `uploaded` and `exported` days are
    Bratislava days. Text matches ignore case and diacritics; budget, MD and DAL match by
    prefix (`632` or `632005 41`)."""

    text: str | None = None
    supplier_ico: str | None = None
    states: Collection[str] = ()
    series: Collection[str] = ()
    channels: Collection[str] = ()
    needs_review: bool | None = None
    uploaded_by: str | None = None
    issue_from: date | None = None
    issue_to: date | None = None
    due_from: date | None = None
    due_to: date | None = None
    booking_from: date | None = None
    booking_to: date | None = None
    uploaded_from: date | None = None
    uploaded_to: date | None = None
    exported_from: date | None = None
    exported_to: date | None = None
    paid_from: date | None = None
    paid_to: date | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    budget: str | None = None
    md: str | None = None
    dal: str | None = None


def day_start(day: date) -> datetime:
    """The instant a Bratislava day starts, in UTC."""
    return datetime.combine(day, time.min, BRATISLAVA).astimezone(UTC)


def day_end(day: date) -> datetime:
    """The instant the next Bratislava day starts, in UTC (an exclusive end)."""
    return day_start(day + timedelta(days=1))


@dataclass(frozen=True, slots=True)
class InvoiceRowView:
    """One row of the table."""

    id: str
    state: str
    channel: str
    source_ref: str | None
    needs_review: bool
    series: str | None
    document_number: str | None
    booking_date: date | None
    supplier_name: str | None
    supplier_ico: str | None
    invoice_number: str | None
    variable_symbol: str | None
    issue_date: date | None
    due_date: date | None
    supply_date: date | None
    gross: Decimal | None
    currency: str | None
    uploaded_at: datetime
    uploaded_by: str | None
    exported_at: datetime | None
    paid_on: date | None
    budget_keys: tuple[str, ...] = ()
    md: tuple[str, ...] = ()
    dal: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InvoicePage:
    items: list[InvoiceRowView]
    total: int


@dataclass(frozen=True, slots=True)
class SupplierView:
    ico: str | None
    name: str | None
    invoices: int


@dataclass(frozen=True, slots=True)
class HistoryView:
    items: list[HistoryEntryView]
    names: dict[str, str] = field(default_factory=dict)
    """The people in it, ID → name."""


class InvoiceQueries(Protocol):
    def page(
        self,
        customer_id: str,
        criteria: InvoiceFilter,
        sort: Sort,
        *,
        offset: int,
        limit: int,
    ) -> InvoicePage: ...

    def ids(self, customer_id: str, criteria: InvoiceFilter, sort: Sort) -> list[str]:
        """Every invoice the filter finds, in the sort's order (for an export of a filter)."""
        ...

    def suppliers(self, customer_id: str, text: str | None, *, limit: int) -> list[SupplierView]:
        """The customer's suppliers whose name or IČO matches, with their invoice counts."""
        ...


class PeopleNames(Protocol):
    def names(self, user_ids: Collection[str]) -> dict[str, str]:
        """The names of the users with these IDs (those that still have one)."""
        ...


class QueriesUnitOfWork(InvoicingUnitOfWork, Protocol):
    @property
    def invoice_queries(self) -> InvoiceQueries: ...

    @property
    def people(self) -> PeopleNames: ...


def list_invoices(
    ctx: RequestContext,
    uow: QueriesUnitOfWork,
    customer_id: str,
    criteria: InvoiceFilter,
    sort: Sort,
    *,
    page: int = 1,
    size: int = 50,
) -> InvoicePage:
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    size = max(1, min(size, MAX_SIZE))
    with uow:
        return uow.invoice_queries.page(
            customer_id, criteria, sort, offset=(max(page, 1) - 1) * size, limit=size
        )


def find_suppliers(
    ctx: RequestContext, uow: QueriesUnitOfWork, customer_id: str, text: str | None
) -> list[SupplierView]:
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        return uow.invoice_queries.suppliers(customer_id, text, limit=20)


def get_invoice(
    ctx: RequestContext, uow: InvoicingUnitOfWork, customer_id: str, invoice_id: str
) -> InvoiceView:
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        return InvoiceView.of(uow.invoices.get(customer_id, invoice_id))


def invoice_history(
    ctx: RequestContext, uow: QueriesUnitOfWork, customer_id: str, invoice_id: str
) -> HistoryView:
    """The invoice's transitions, oldest first, with who made them (plan §10.4)."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        uow.invoices.get(customer_id, invoice_id)  # NotFound for a foreign invoice
        entries = uow.invoices.history(customer_id, invoice_id)
        people: Sequence[str] = [
            p for e in entries for p in (e.actor_id, e.real_actor_id) if p is not None
        ]
        names = uow.people.names(set(people))
    return HistoryView([HistoryEntryView.of(e) for e in entries], names)
