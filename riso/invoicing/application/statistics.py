"""What the dashboards read about a customer's invoices (plan §10.2, §10.8): one fact per
invoice with the columns the statistics need, the booked line amounts per budget key for the
drawdown, and whether anything was ever booked. Read only; the reporting context computes
the statistics from these (plan §2 decision 67)."""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from riso.identity import Permission
from riso.invoicing.application.uow import InvoicingUnitOfWork
from riso.invoicing.domain.invoice import InvoiceState
from riso.shared.context import RequestContext

BOOKED_STATES: tuple[str, ...] = (
    InvoiceState.BOOKED.value,
    InvoiceState.EXPORTED.value,
    InvoiceState.PAID.value,
)
"""Booked, for the statistics: booked, exported or paid (decision 67)."""

OPEN_STATES: tuple[str, ...] = (
    InvoiceState.UPLOADED.value,
    InvoiceState.EXTRACTING.value,
    InvoiceState.EXTRACTED.value,
    InvoiceState.CHECKED.value,
    InvoiceState.NEEDS_REVIEW.value,
    InvoiceState.READY.value,
)
"""Still on its way to booking: what "Vyžaduje pozornosť" counts as waiting."""


@dataclass(frozen=True, slots=True)
class LineFact:
    """A line of a booked invoice: its function and amount."""

    oddiel: str
    trieda: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class InvoiceFact:
    id: str
    state: str
    series: str | None
    credit_note: bool
    """Printed as a credit note, or with a negative total."""
    gross: Decimal | None
    """The total; negative for a credit note."""
    supplier_ico: str | None
    supplier_name: str | None
    needs_review: bool
    """For a booked invoice: whether its proposal needed review."""
    uploaded_at: datetime
    booked_at: datetime | None
    lines: tuple[LineFact, ...] = ()


@dataclass(frozen=True, slots=True)
class CustomerCounts:
    """One customer's numbers for an overview row (plan §10.8): the invoices uploaded in a
    period, by their state now, and the invoices booked in it."""

    uploaded: int
    by_state: dict[str, int]
    booked: int


class InvoiceStatistics(Protocol):
    def uploaded(self, customer_id: str, start: datetime, end: datetime) -> list[InvoiceFact]:
        """The invoices uploaded in [start, end), without lines."""
        ...

    def booked(
        self, customer_id: str, start: datetime, end: datetime, *, lines: bool = False
    ) -> list[InvoiceFact]:
        """The booked invoices (`BOOKED_STATES`) booked in [start, end), with their lines
        when asked."""
        ...

    def drawn(self, customer_id: str, year: int) -> dict[str, Decimal]:
        """Budget key → the sum of the lines of the booked invoices whose booking date is in
        the year (the budget year)."""
        ...

    def any_booked(self, customer_id: str) -> bool: ...

    def counts(
        self, customer_ids: Collection[str], start: datetime, end: datetime
    ) -> dict[str, CustomerCounts]:
        """Per customer, the overview numbers for [start, end); every given customer has an
        entry."""
        ...

    def total_uploaded(self, start: datetime, end: datetime) -> int:
        """Invoices uploaded in [start, end) across every customer (the platform count)."""
        ...


class StatisticsUnitOfWork(InvoicingUnitOfWork, Protocol):
    @property
    def invoice_statistics(self) -> InvoiceStatistics: ...


@dataclass(frozen=True, slots=True)
class BookedWindow:
    """The booked invoices of `[start, end)`, and those of `[lines_start, end)` with their
    lines (the selected month within the twelve months)."""

    start: datetime
    lines_start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class InvoiceFacts:
    uploaded: list[InvoiceFact]
    booked: list[InvoiceFact]
    """Booked in the whole window, the month's with their lines."""
    drawn: dict[str, Decimal]
    any_booked: bool


def invoice_facts(
    ctx: RequestContext,
    uow: StatisticsUnitOfWork,
    customer_id: str,
    *,
    uploaded: tuple[datetime, datetime],
    booked: BookedWindow,
    budget_year: int,
) -> InvoiceFacts:
    """The facts a customer's dashboard is computed from, read in one unit of work."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        stats = uow.invoice_statistics
        earlier = stats.booked(customer_id, booked.start, booked.lines_start)
        month = stats.booked(customer_id, booked.lines_start, booked.end, lines=True)
        return InvoiceFacts(
            uploaded=stats.uploaded(customer_id, *uploaded),
            booked=earlier + month,
            drawn=stats.drawn(customer_id, budget_year),
            any_booked=stats.any_booked(customer_id),
        )


def customer_counts(
    uow: StatisticsUnitOfWork, customer_ids: Collection[str], start: datetime, end: datetime
) -> dict[str, CustomerCounts]:
    """The overview numbers of customers the caller was already allowed to see (the
    reporting context checks the provider or platform permission first)."""
    with uow:
        return uow.invoice_statistics.counts(customer_ids, start, end)


def invoices_uploaded(uow: StatisticsUnitOfWork, start: datetime, end: datetime) -> int:
    """The platform's count; the caller checked the platform permission."""
    with uow:
        return uow.invoice_statistics.total_uploaded(start, end)
