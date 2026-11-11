"""Domov, the customer's dashboard (plan §10.2, §2 decision 67).

A month is a Bratislava month. The month's uploads give "Nahrané", and those of them now
`extracted`, `needs_review` and `extraction_failed` give "Čaká na kontrolu", "Na kontrolu"
and "Neúspešné". Every booked statistic counts the invoices booked, exported or paid whose
booking in riso (`booked_at`) fell in the month or day; amounts are gross, credit notes
negative. The budget drawdown follows the budget year: the lines of the invoices booked with
a booking date in the year, against the expense budget's amounts (adjusted, else approved),
and is absent when the budget has no amounts. "Vyžaduje pozornosť" and the onboarding
checklist describe the customer now, whatever the month.
"""

import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Protocol

from riso.codelists import (
    BudgetAmountView,
    CodelistsUnitOfWork,
    HealthSeverity,
    expense_budget,
    function_names,
    knowledge_health,
)
from riso.identity import Permission
from riso.invoicing import (
    OPEN_STATES,
    BookedWindow,
    InvoiceFact,
    InvoiceFilter,
    InvoiceRowView,
    QueriesUnitOfWork,
    Sort,
    StatisticsUnitOfWork,
    invoice_facts,
    list_invoices,
    supplier_memory,
)
from riso.shared.clock import BRATISLAVA, local_date
from riso.shared.context import RequestContext
from riso.tenancy import CustomerView, TenancyUnitOfWork, get_customer

ZERO = Decimal("0.00")
TOP = 10
"""Suppliers in each top list."""
MONTHS = 12
"""Months in the totals' series, ending with the chosen one."""
ATTENTION = 5
"""Invoices in each of the attention lists."""


class DashboardUnitOfWork(
    StatisticsUnitOfWork, QueriesUnitOfWork, CodelistsUnitOfWork, TenancyUnitOfWork, Protocol
):
    pass


@dataclass(frozen=True, slots=True, order=True)
class Month:
    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12 or not 2000 <= self.year <= 2100:
            raise ValueError(f"no month {self.year}-{self.month}")

    @classmethod
    def parse(cls, text: str) -> "Month":
        """`2026-11`."""
        year, _, month = text.partition("-")
        if len(year) != 4 or len(month) != 2 or not (year + month).isdigit():
            raise ValueError(f"not a month: {text!r}")
        return cls(int(year), int(month))

    @classmethod
    def of(cls, day: date) -> "Month":
        return cls(day.year, day.month)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    def shifted(self, months: int) -> "Month":
        index = self.year * 12 + self.month - 1 + months
        return Month(index // 12, index % 12 + 1)

    @property
    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def last_day(self) -> date:
        return self.shifted(1).first_day - timedelta(days=1)

    def days(self) -> list[date]:
        return [self.first_day + timedelta(days=n) for n in range(self.last_day.day)]

    @property
    def start(self) -> datetime:
        """The instant the month starts in Bratislava, in UTC."""
        return datetime.combine(self.first_day, time.min, BRATISLAVA).astimezone(UTC)

    @property
    def end(self) -> datetime:
        """The instant the next month starts (an exclusive end)."""
        return self.shifted(1).start

    def holds(self, instant: datetime) -> bool:
        return self.start <= instant < self.end


@dataclass(frozen=True, slots=True)
class Tiles:
    uploaded: int
    waiting: int
    """Extracted, waiting for the check step."""
    review: int
    failed: int
    """The extraction failed."""
    booked: int
    booked_total: Decimal


@dataclass(frozen=True, slots=True)
class DayTotal:
    day: date
    count: int
    total: Decimal


@dataclass(frozen=True, slots=True)
class TypeTotal:
    series: str | None
    credit_note: bool
    count: int
    total: Decimal


@dataclass(frozen=True, slots=True)
class SupplierTotal:
    ico: str | None
    name: str | None
    count: int
    total: Decimal


@dataclass(frozen=True, slots=True)
class UnitTotal:
    function: str
    """Oddiel and trieda as the budget key writes them: `09 111`."""
    code: str | None
    """The COFOG code (`09.1.1.1`) and its name, when the year's list has them."""
    name: str | None
    invoices: int
    total: Decimal
    """The sum of the booked lines of the function."""


@dataclass(frozen=True, slots=True)
class MonthTotal:
    month: str
    count: int
    total: Decimal


@dataclass(frozen=True, slots=True)
class Review:
    booked: int
    reviewed: int
    """Booked invoices whose proposal needed review."""
    median_seconds: int | None
    """From upload to booking, over the month's bookings."""

    @property
    def rate(self) -> float | None:
        return self.reviewed / self.booked if self.booked else None


@dataclass(frozen=True, slots=True)
class BudgetRow:
    key: str
    description: str | None
    budgeted: Decimal
    drawn: Decimal

    @property
    def share(self) -> float | None:
        return float(self.drawn / self.budgeted) if self.budgeted else None


@dataclass(frozen=True, slots=True)
class Budget:
    year: int
    rows: list[BudgetRow]
    """The positions with an amount, by key."""
    budgeted: Decimal
    drawn: Decimal
    """Drawn on those positions."""
    elsewhere: Decimal
    """Drawn on positions without an amount."""


@dataclass(frozen=True, slots=True)
class AttentionItem:
    id: str
    state: str
    supplier_name: str | None
    source_ref: str | None
    uploaded_at: datetime

    @classmethod
    def of(cls, row: InvoiceRowView) -> "AttentionItem":
        return cls(row.id, row.state, row.supplier_name, row.source_ref, row.uploaded_at)


@dataclass(frozen=True, slots=True)
class Warning:
    code: str
    subject: str
    kind: str | None


@dataclass(frozen=True, slots=True)
class Attention:
    failed: list[AttentionItem]
    """The newest failed extractions."""
    failed_total: int
    waiting: list[AttentionItem]
    """The open invoices uploaded longest ago."""
    waiting_total: int
    warnings: list[Warning]
    """The knowledge health report's errors for the year (missing lists, no knowledge)."""


@dataclass(frozen=True, slots=True)
class Onboarding:
    year: int
    profile: bool
    """The address and the bank account are filled in."""
    codelists: bool
    """No list the engine needs is missing for the year."""
    health: bool
    """The knowledge health report has no errors for the year."""
    first_booked: bool

    @property
    def done(self) -> bool:
        return self.profile and self.codelists and self.health and self.first_booked


@dataclass(frozen=True, slots=True)
class MonthStatistics:
    tiles: Tiles
    per_day: list[DayTotal]
    by_type: list[TypeTotal]
    suppliers_by_count: list[SupplierTotal]
    suppliers_by_amount: list[SupplierTotal]
    units: list[UnitTotal]
    months: list[MonthTotal]
    review: Review


@dataclass(frozen=True, slots=True)
class DashboardView:
    month: str
    statistics: MonthStatistics
    budget: Budget | None
    attention: Attention
    onboarding: Onboarding


def _sum(amounts: Iterable[Decimal | None]) -> Decimal:
    return sum((a for a in amounts if a is not None), ZERO)


@dataclass(slots=True)
class _Group:
    count: int = 0
    total: Decimal = ZERO
    name: str | None = None
    invoices: set[str] = field(default_factory=set)

    def add(self, amount: Decimal | None) -> None:
        self.count += 1
        self.total += amount or ZERO


def _suppliers(booked: list[InvoiceFact]) -> list[SupplierTotal]:
    groups: dict[tuple[str | None, str | None], _Group] = defaultdict(_Group)
    for fact in booked:
        key = (fact.supplier_ico, None) if fact.supplier_ico else (None, fact.supplier_name)
        group = groups[key]
        group.add(fact.gross)
        group.name = fact.supplier_name or group.name
    return [SupplierTotal(ico, g.name, g.count, g.total) for (ico, _), g in groups.items()]


def month_statistics(
    month: Month,
    uploaded: Iterable[InvoiceFact],
    booked: Iterable[InvoiceFact],
    names: Mapping[str, tuple[str, str]],
) -> MonthStatistics:
    """The month's numbers from the invoices uploaded in it and those booked in the twelve
    months ending with it (the month's with their lines). `names`: function → COFOG code
    and name."""
    uploads = [f for f in uploaded if month.holds(f.uploaded_at)]
    window = [(f, f.booked_at) for f in booked if f.booked_at is not None]
    in_month = [(f, at) for f, at in window if month.holds(at)]
    facts = [f for f, _ in in_month]
    states = [f.state for f in uploads]
    tiles = Tiles(
        uploaded=len(states),
        waiting=states.count("extracted"),
        review=states.count("needs_review"),
        failed=states.count("extraction_failed"),
        booked=len(facts),
        booked_total=_sum(f.gross for f in facts),
    )

    days: dict[date, _Group] = {day: _Group() for day in month.days()}
    for fact, at in in_month:
        days[local_date(at)].add(fact.gross)
    per_day = [DayTotal(day, g.count, g.total) for day, g in days.items()]

    types: dict[tuple[str | None, bool], _Group] = defaultdict(_Group)
    for fact in facts:
        types[(fact.series, fact.credit_note)].add(fact.gross)
    by_type = [
        TypeTotal(series, credit, g.count, g.total)
        for (series, credit), g in sorted(types.items(), key=lambda t: (t[0][0] or "", t[0][1]))
    ]

    suppliers = _suppliers(facts)
    by_count = sorted(suppliers, key=lambda s: (-s.count, -s.total, s.name or "", s.ico or ""))
    by_amount = sorted(suppliers, key=lambda s: (-s.total, -s.count, s.name or "", s.ico or ""))

    units: dict[str, _Group] = defaultdict(_Group)
    for fact in facts:
        for line in fact.lines:
            group = units[f"{line.oddiel} {line.trieda}"]
            group.total += line.amount
            group.invoices.add(fact.id)
    unit_totals = []
    for function, g in units.items():
        code, name = names.get(function) or (None, None)
        unit_totals.append(UnitTotal(function, code, name, len(g.invoices), g.total))
    unit_totals.sort(key=lambda u: (-u.total, u.function))

    series = [month.shifted(-n) for n in range(MONTHS - 1, -1, -1)]
    per_month: dict[Month, _Group] = {m: _Group() for m in series}
    for fact, at in window:
        key = Month.of(local_date(at))
        if key in per_month:
            per_month[key].add(fact.gross)
    months = [MonthTotal(str(m), g.count, g.total) for m, g in per_month.items()]

    waits = [(at - fact.uploaded_at).total_seconds() for fact, at in in_month]
    review = Review(
        booked=len(facts),
        reviewed=sum(1 for f in facts if f.needs_review),
        median_seconds=round(statistics.median(waits)) if waits else None,
    )
    return MonthStatistics(
        tiles=tiles,
        per_day=per_day,
        by_type=by_type,
        suppliers_by_count=by_count[:TOP],
        suppliers_by_amount=by_amount[:TOP],
        units=unit_totals,
        months=months,
        review=review,
    )


def budget_drawdown(
    year: int, positions: Iterable[BudgetAmountView], drawn: Mapping[str, Decimal]
) -> Budget | None:
    """The drawdown of the year's positions that have an amount; None when none has."""
    rows = sorted(
        (
            BudgetRow(p.key, p.description, p.budgeted, drawn.get(p.key, ZERO))
            for p in positions
            if p.budgeted is not None
        ),
        key=lambda r: r.key,
    )
    if not rows:
        return None
    keys = {r.key for r in rows}
    return Budget(
        year=year,
        rows=rows,
        budgeted=_sum(r.budgeted for r in rows),
        drawn=_sum(r.drawn for r in rows),
        elsewhere=_sum(amount for key, amount in drawn.items() if key not in keys),
    )


def _profile_complete(customer: CustomerView) -> bool:
    return customer.address is not None and customer.iban is not None


def _attention_rows(
    ctx: RequestContext,
    uow: QueriesUnitOfWork,
    customer_id: str,
    states: tuple[str, ...],
    sort: Sort,
) -> tuple[list[AttentionItem], int]:
    page = list_invoices(
        ctx, uow, customer_id, InvoiceFilter(states=states), sort, page=1, size=ATTENTION
    )
    return [AttentionItem.of(r) for r in page.items], page.total


def customer_dashboard(
    ctx: RequestContext,
    uow_factory: Callable[[], DashboardUnitOfWork],
    customer_id: str,
    month: Month,
) -> DashboardView:
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    first = month.shifted(-(MONTHS - 1))
    facts = invoice_facts(
        ctx,
        uow_factory(),
        customer_id,
        uploaded=(month.start, month.end),
        booked=BookedWindow(first.start, month.start, month.end),
        budget_year=month.year,
    )
    customer = get_customer(ctx, uow_factory(), customer_id)
    uow = uow_factory()
    with uow:
        today = local_date(uow.clock.now())
        names = function_names(uow, month.year)
        positions = expense_budget(uow, customer_id, month.year)
        memory = supplier_memory(uow, customer_id, customer.ico)
    findings = knowledge_health(ctx, uow_factory(), customer_id, today.year, memory)
    errors = [f for f in findings if f.severity is HealthSeverity.ERROR]
    failed, failed_total = _attention_rows(
        ctx, uow_factory(), customer_id, ("extraction_failed",), Sort("uploaded_at", True)
    )
    waiting, waiting_total = _attention_rows(
        ctx, uow_factory(), customer_id, OPEN_STATES, Sort("uploaded_at", False)
    )
    return DashboardView(
        month=str(month),
        statistics=month_statistics(month, facts.uploaded, facts.booked, names),
        budget=budget_drawdown(month.year, positions, facts.drawn),
        attention=Attention(
            failed=failed,
            failed_total=failed_total,
            waiting=waiting,
            waiting_total=waiting_total,
            warnings=[
                Warning(f.code.value, f.subject, f.kind.value if f.kind else None) for f in errors
            ],
        ),
        onboarding=Onboarding(
            year=today.year,
            profile=_profile_complete(customer),
            codelists=not any(f.code.value == "list_missing" for f in errors),
            health=not errors,
            first_booked=facts.any_booked,
        ),
    )
