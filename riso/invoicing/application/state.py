"""What the engine keeps between invoices, on the database (plan §4.3): the customer's
supplier memory and counters as the engine's contracts, and the ways other parts fill them:
the initial state when seeding, past bookings (P2-M3-T05) and a customer copy.

Every function works in the caller's open unit of work, so an import or a copy commits its
changes to the memory together with its own.

A used number from outside riso is held in its series when it fits the pattern of its
series code (the counters' series of the number's year); one of an unknown series, one that
does not fit, or one of a series numbered per month (bank statements) is kept loose
(`add_loose`), so the engine still warns about it, as the demo's counters file did. Counters
of series numbered per month are not kept: riso numbers only supplier invoices.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from riso.contracts import Counters, Precedent, SupplierMemory
from riso.invoicing.application.numbering import FALLBACK, series_for
from riso.invoicing.application.uow import InvoicingUnitOfWork
from riso.invoicing.domain.numbering import NumberSeries, numberable
from riso.reference import parse_number


@dataclass(frozen=True, slots=True)
class PastPrecedent:
    """One past booking for the memory."""

    supplier_ico: str
    supplier_name: str
    precedent: Precedent


def supplier_memory(uow: InvoicingUnitOfWork, customer_id: str, ico: str) -> SupplierMemory:
    return uow.supplier_memory.memory(customer_id, ico)


def counters(uow: InvoicingUnitOfWork, customer_id: str, ico: str) -> Counters:
    """The counters per `<series>/<year>` and every number used, in the order first used."""
    return Counters(
        entity_ico=ico,
        last_used={s.key: s.last_used for s in uow.number_series.of_customer(customer_id)},
        used_numbers=uow.number_series.used_numbers(customer_id),
    )


class _Batch:
    """The series a batch of numbers touches, each saved once at the end."""

    def __init__(
        self, uow: InvoicingUnitOfWork, customer_id: str, patterns: Mapping[str, str]
    ) -> None:
        self._uow, self._customer_id, self._patterns = uow, customer_id, patterns
        self._at = uow.clock.now()
        self._found: dict[tuple[str, int], NumberSeries] = {}

    def series(self, code: str, year: int) -> NumberSeries:
        key = (code, year)
        if key not in self._found:
            pattern = self._patterns.get(code, FALLBACK.format(code=code))
            self._found[key] = series_for(
                self._uow, self._customer_id, code, year, self._at, pattern=pattern
            )
        return self._found[key]

    def _numbered(self, code: str) -> bool:
        return numberable(self._patterns.get(code, FALLBACK.format(code=code)))

    def raise_counter(self, key: str, value: int) -> None:
        code, year = key.split("/")
        if self._numbered(code):
            self.series(code, int(year)).raise_counter(value, self._at)

    def mark_used(self, number: str) -> None:
        code = number.split("/")[0]
        pattern = self._patterns.get(code)
        parsed = parse_number(pattern, number) if pattern else None
        if parsed is None or parsed.year is None or not self._numbered(code):
            self._uow.number_series.add_loose(self._customer_id, number)
            return
        series = self.series(code, 2000 + parsed.year)
        series.mark_external(parsed.sequence, self._uow.ids.new(), self._at)

    def save(self) -> None:
        for series in self._found.values():
            self._uow.number_series.save(series)


def restore_state(
    uow: InvoicingUnitOfWork,
    customer_id: str,
    memory: SupplierMemory,
    counters: Counters,
    patterns: Mapping[str, str],
) -> None:
    """Seeding: the memory and counters as the initial state's files have them, with the
    series patterns of their year. Suppliers keep their order and precedents theirs; used
    numbers keep the order they were taken in."""
    for record in memory.suppliers:
        for precedent in reversed(record.precedents):
            uow.supplier_memory.add_precedent(customer_id, record.ico, record.name, precedent)
    batch = _Batch(uow, customer_id, patterns)
    for key, last_used in counters.last_used.items():
        batch.raise_counter(key, last_used)
    for number in counters.used_numbers:
        batch.mark_used(number)
    batch.save()


def add_past_bookings(
    uow: InvoicingUnitOfWork,
    customer_id: str,
    bookings: Sequence[PastPrecedent],
    numbers: Sequence[str],
    counter_rises: Mapping[str, int],
    patterns: Mapping[str, str],
) -> None:
    """A past-bookings import (as `merge_plan` merges it): the precedents join their
    suppliers' (newest first by booking date), the counters rise to at least the given
    values, and the numbers become used."""
    grouped: dict[str, list[PastPrecedent]] = {}
    for booking in bookings:
        grouped.setdefault(booking.supplier_ico, []).append(booking)
    for ico, items in grouped.items():
        uow.supplier_memory.add_past(
            customer_id, ico, items[0].supplier_name, [item.precedent for item in items]
        )
    batch = _Batch(uow, customer_id, patterns)
    for key, after in counter_rises.items():
        batch.raise_counter(key, after)
    for number in numbers:
        batch.mark_used(number)
    batch.save()


def copy_memory(uow: InvoicingUnitOfWork, source_id: str, target_id: str) -> int:
    """A customer copy's supplier memory; a target with a memory keeps it (0)."""
    return uow.supplier_memory.copy(source_id, target_id)
