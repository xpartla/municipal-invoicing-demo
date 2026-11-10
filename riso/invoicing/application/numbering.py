"""Number series (plan §7.2, §2 decisions 61 and 62): the series of a year with their
counters, used numbers and gaps; the audited edit of the counter; and taking a number when
an invoice is booked.

A series row is made the first time it is needed, with the pattern of the year's document
series list.
"""

from dataclasses import dataclass
from datetime import datetime

from riso.identity import Permission
from riso.invoicing.application.uow import InvoicingUnitOfWork
from riso.invoicing.domain.numbering import Newcomer, NumberSeries, Placement
from riso.shared.context import RequestContext
from riso.shared.errors import InvalidState, NotFound
from riso.shared.values import clean_name

FALLBACK = "{code}/XXX/RR"
"""The pattern of a series the year's list does not have (an old counter, an import)."""


@dataclass(frozen=True, slots=True)
class UsedNumberView:
    number: str
    sequence: int
    kind: str
    invoice_id: str | None
    frozen: bool


@dataclass(frozen=True, slots=True)
class SeriesView:
    series: str
    year: int
    pattern: str
    last_used: int
    last_used_number: str | None
    next_number: str
    used: tuple[UsedNumberView, ...]
    gaps: tuple[str, ...]
    stored: bool
    """False for a series of the year's list that has never been used."""

    @classmethod
    def of(cls, series: NumberSeries, *, stored: bool = True) -> "SeriesView":
        return cls(
            series=series.series,
            year=series.year,
            pattern=series.pattern,
            last_used=series.last_used,
            last_used_number=series.number(series.last_used) if series.last_used else None,
            next_number=series.number(series.last_used + 1),
            used=tuple(
                UsedNumberView(
                    series.number(h.sequence), h.sequence, h.kind.value, h.invoice_id, h.frozen
                )
                for h in sorted(series.holders, key=lambda h: h.sequence)
            ),
            gaps=tuple(series.number(n) for n in series.gaps()),
            stored=stored,
        )


def series_for(
    uow: InvoicingUnitOfWork,
    customer_id: str,
    code: str,
    year: int,
    at: datetime,
    *,
    pattern: str | None = None,
) -> NumberSeries:
    """The customer's series of the year, made (and added) when it is first needed, with
    the pattern of the year's document series list, or the given one (imports and the
    initial state name series and years the lists may not have). Without either it is
    refused."""
    found = uow.number_series.find(customer_id, code, year)
    if found is not None:
        return found
    pattern = uow.series_patterns.patterns(customer_id, year).get(code) or pattern
    if pattern is None:
        raise InvalidState(f"the {year} document series list has no series {code}")
    series = NumberSeries.new(uow.ids.new(), customer_id, code, year, pattern, at)
    uow.number_series.add(series)
    return series


def take_number(
    uow: InvoicingUnitOfWork,
    customer_id: str,
    code: str,
    year: int,
    newcomer: Newcomer,
    *,
    requested: str | None,
) -> Placement:
    """Books the newcomer's number in the open unit of work (whose BEGIN IMMEDIATE keeps two
    bookings from taking the same one). Raises `NumberFrozen`. The caller renumbers the
    invoices of the placement's shifts."""
    at = uow.clock.now()
    series = series_for(uow, customer_id, code, year, at)
    for other in uow.number_series.holding(customer_id, newcomer.invoice_id):
        if other.id != series.id and other.drop_reservation(newcomer.invoice_id, at):
            uow.number_series.save(other)
    placement = series.allocate(newcomer, uow.ids.new(), at, requested=requested)
    uow.number_series.save(series)
    return placement


def preview_number(
    uow: InvoicingUnitOfWork, customer_id: str, code: str, year: int, newcomer: Newcomer
) -> Placement:
    """Where booking would put the newcomer, without changing anything."""
    at = uow.clock.now()
    series = uow.number_series.find(customer_id, code, year)
    if series is None:
        pattern = uow.series_patterns.patterns(customer_id, year).get(code)
        if pattern is None:
            raise InvalidState(f"the {year} document series list has no series {code}")
        series = NumberSeries.new("preview", customer_id, code, year, pattern, at)
    return series.preview(newcomer)


def list_series(
    ctx: RequestContext, uow: InvoicingUnitOfWork, customer_id: str, year: int
) -> list[SeriesView]:
    """The year's series: the customer's invoice series (used or not), then any other series
    with a counter (past bookings), as the demo's counters page listed them."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        stored = {s.series: s for s in uow.number_series.of_customer(customer_id, year=year)}
        patterns = uow.series_patterns.patterns(customer_id, year)
        at = uow.clock.now()
        views = []
        for code in uow.series_patterns.invoice_series(customer_id, year):
            if code in stored:
                views.append(SeriesView.of(stored.pop(code)))
            elif code in patterns:
                transient = NumberSeries.new("", customer_id, code, year, patterns[code], at)
                views.append(SeriesView.of(transient, stored=False))
        views += [SeriesView.of(s) for s in stored.values()]
    return views


def set_last_used(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    customer_id: str,
    code: str,
    year: int,
    value: int,
) -> SeriesView:
    """Edits the counter (until it syncs with TOPSET), audited with before and after. It
    cannot go below a number held."""
    ctx.require(Permission.CODELISTS_EDIT, customer_id)
    code = clean_name(code)
    with uow:
        at = uow.clock.now()
        try:
            series = series_for(uow, customer_id, code, year, at)
        except InvalidState as exc:
            raise NotFound(str(exc)) from exc
        before = series.set_last_used(value, at)
        uow.number_series.save(series)
        uow.audit.record(
            ctx,
            "number_series.last_used_set",
            target_type="number_series",
            target_id=series.id,
            customer_id=customer_id,
            details={"series": code, "year": year, "before": before, "after": value},
        )
        uow.commit()
    return SeriesView.of(series)
