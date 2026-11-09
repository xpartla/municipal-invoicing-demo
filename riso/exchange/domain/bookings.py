"""Past bookings (plan §9.1, §9.2; P2-M3-T05): a book of received invoices (kniha došlých
faktúr) becomes supplier precedents with `source: "import"`, its document numbers are marked
used, and the counters' last used rise to the highest number per series and year.

The file has one row per line; the mapping groups the rows of one supplier's IČO and document
number into a booking (`records.py`). Here a booking is parsed through the contracts (an IČO
of eight digits, budget keys `EK zdroj oddiel trieda analytika`, accounts `SU AU`, amounts
with two decimals): a booking that does not parse is an error with its rows. Accounts written
`518001`, `518.001` or `518/001` are read as `518 001`, and an IČO with fewer digits gets its
leading zeros.

The plan (`plan_bookings`) compares the bookings with the customer's memory and counters:

- a booking the memory already has (the same supplier and document number) is skipped, with
  a warning; applying the same book twice changes nothing;
- each number is marked used, and the counter of its series and year rises to it when the
  number fits the series' pattern (the active document series list);
- warnings name what the engine will not use: a budget key outside the year's expense
  positions, an account outside the chart, a number of no known series, a number another
  booking already took.

`merge_plan` writes a plan into a memory and counters (the demo files' adapter uses it). A
supplier's precedents stay newest first by booking date, as the engine ranks them.
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import ValidationError

from riso.contracts import Counters, Precedent, PrecedentLine, SupplierMemory, SupplierRecord
from riso.exchange.domain.records import Record
from riso.reference import parse_number
from riso.shared import ico_is_valid

_ACCOUNT = re.compile(r"^(\d{3})\s*[./-]?\s*(\d{3})$")


@dataclass(frozen=True, slots=True)
class PastBooking:
    supplier_ico: str
    supplier_name: str
    precedent: Precedent
    rows: tuple[int, ...]

    @property
    def number(self) -> str:
        assert self.precedent.document_number is not None
        return self.precedent.document_number

    @property
    def key(self) -> str:
        return f"{self.supplier_ico} {self.number}"

    def summary(self) -> dict[str, Any]:
        """The booking as the report shows it."""
        return {
            "supplier_ico": self.supplier_ico,
            "supplier_name": self.supplier_name,
            **self.precedent.model_dump(mode="json", exclude={"source"}),
            "rows": list(self.rows),
        }


@dataclass(frozen=True, slots=True)
class BookingProblem:
    key: str
    rows: tuple[int, ...]
    field: str | None
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class BookingWarning:
    code: str
    rows: tuple[int, ...]
    message: str
    key: str | None = None
    value: str | None = None


def _account(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    match = _ACCOUNT.match(value.strip())
    return f"{match[1]} {match[2]}" if match else value.strip()


def _budget_key(value: Any) -> Any:
    return " ".join(value.split()) if isinstance(value, str) else value


def _ico(value: Any) -> Any:
    if isinstance(value, str) and value.isdigit() and value.isascii() and len(value) < 8:
        return value.zfill(8)
    return value


def _problems(exc: ValidationError, key: str, rows: tuple[int, ...]) -> list[BookingProblem]:
    return [
        BookingProblem(
            key,
            rows,
            ".".join(str(part) for part in error["loc"]) or None,
            error["type"],
            error["msg"],
        )
        for error in exc.errors()
    ]


def parse_bookings(
    records: Iterable[Record],
) -> tuple[list[PastBooking], list[BookingProblem]]:
    """The mapped records as bookings, and the problems of those that do not parse."""
    bookings: list[PastBooking] = []
    problems: list[BookingProblem] = []
    for record in records:
        values = record.values
        ico = _ico(values.get("supplier_ico"))
        key = f"{ico} {values.get('document_number')}"
        lines: list[PrecedentLine] = []
        line_problems: list[BookingProblem] = []
        for index, line in enumerate(values.get("lines", ())):
            try:
                lines.append(
                    PrecedentLine(
                        budget_key=_budget_key(line.get("budget_key")),
                        md=_account(line.get("md")),
                        dal=_account(line.get("dal")),
                        budget_text=line.get("budget_text") or "",
                        posting_text=line.get("posting_text") or "",
                    )
                )
            except ValidationError as exc:
                row = (record.rows[index],) if index < len(record.rows) else record.rows
                line_problems += _problems(exc, key, row)
        if line_problems:
            problems += line_problems
            continue
        try:
            precedent = Precedent(
                document_number=values.get("document_number"),
                booking_date=values.get("booking_date"),
                amount=values.get("amount"),
                variable_symbol=values.get("variable_symbol"),
                lines=lines,
                source="import",
            )
            supplier = SupplierRecord(
                ico=ico, name=values.get("supplier_name") or ico, precedents=[precedent]
            )
        except ValidationError as exc:
            problems += _problems(exc, key, record.rows)
            continue
        bookings.append(PastBooking(supplier.ico, supplier.name, precedent, record.rows))
    return bookings, problems


@dataclass(frozen=True, slots=True)
class CounterRise:
    key: str
    """`<series>/<year>`, as the counters keep it."""
    before: int
    after: int


@dataclass(frozen=True, slots=True)
class BookingsPlan:
    new: tuple[PastBooking, ...]
    present: tuple[PastBooking, ...]
    """Bookings the memory already has; skipped."""
    numbers: tuple[str, ...]
    """Numbers to mark used (those not yet used)."""
    counters: tuple[CounterRise, ...]
    warnings: tuple[BookingWarning, ...]


def _grouped(code: str, found: Mapping[str, list[int]], message: str) -> list[BookingWarning]:
    return [
        BookingWarning(code, tuple(sorted(rows)), message.format(key=key), key=key, value=key)
        for key, rows in sorted(found.items())
    ]


def plan_bookings(
    bookings: Iterable[PastBooking],
    memory: SupplierMemory,
    counters: Counters,
    *,
    series: Mapping[str, str],
    positions: frozenset[str],
    accounts: frozenset[str],
) -> BookingsPlan:
    """What applying the bookings would do. `series` maps a series code to its pattern
    (`FD` → `FD/XXX/RR`); `positions` are the year's expense position keys and `accounts`
    the chart's, for the warnings."""
    new: list[PastBooking] = []
    present: list[PastBooking] = []
    warnings: list[BookingWarning] = []
    numbers: list[str] = []
    last_used = dict(counters.last_used)
    used = set(counters.used_numbers)
    seen_numbers: dict[str, PastBooking] = {}
    unknown_keys: defaultdict[str, list[int]] = defaultdict(list)
    unknown_accounts: defaultdict[str, list[int]] = defaultdict(list)
    unknown_series: defaultdict[str, list[int]] = defaultdict(list)

    for booking in bookings:
        number = booking.number
        record = memory.find(booking.supplier_ico)
        if record is not None and any(p.document_number == number for p in record.precedents):
            present.append(booking)
            warnings.append(
                BookingWarning(
                    "booking_present",
                    booking.rows,
                    f"{number} of {booking.supplier_ico} is already in the supplier memory; "
                    "skipped",
                    key=booking.key,
                )
            )
        else:
            new.append(booking)
            if not ico_is_valid(booking.supplier_ico):
                warnings.append(
                    BookingWarning(
                        "ico_check_digit",
                        booking.rows,
                        f"IČO {booking.supplier_ico} fails its check digit",
                        key=booking.key,
                        value=booking.supplier_ico,
                    )
                )
            for line, row in zip(booking.precedent.lines, booking.rows, strict=False):
                if line.budget_key not in positions:
                    unknown_keys[line.budget_key].append(row)
                for account in (line.md, line.dal):
                    if account not in accounts:
                        unknown_accounts[account].append(row)
            if number in used:
                warnings.append(
                    BookingWarning(
                        "number_used",
                        booking.rows,
                        f"{number} is already used; the precedent is added",
                        key=booking.key,
                        value=number,
                    )
                )
        earlier = seen_numbers.get(number)
        if earlier is not None and earlier.supplier_ico != booking.supplier_ico:
            warnings.append(
                BookingWarning(
                    "number_repeats",
                    (earlier.rows[0], booking.rows[0]),
                    f"{number} is booked for {earlier.supplier_ico} and {booking.supplier_ico}",
                    key=booking.key,
                    value=number,
                )
            )
        seen_numbers.setdefault(number, booking)

        if number not in used:
            used.add(number)
            numbers.append(number)
        code = number.split("/")[0]
        pattern = series.get(code)
        parsed = parse_number(pattern, number) if pattern else None
        if pattern is None:
            unknown_series[code].append(booking.rows[0])
        elif parsed is None:
            warnings.append(
                BookingWarning(
                    "number_not_in_pattern",
                    booking.rows,
                    f"{number} does not fit the series pattern {pattern}; no counter rises",
                    key=booking.key,
                    value=number,
                )
            )
        elif parsed.year is not None:
            counter = f"{code}/{2000 + parsed.year}"
            last_used[counter] = max(last_used.get(counter, 0), parsed.sequence)

    warnings += _grouped(
        "unknown_budget_key",
        unknown_keys,
        "{key} is not an expense position of the year; the engine does not propose it",
    )
    warnings += _grouped(
        "unknown_account",
        unknown_accounts,
        "{key} is not in the chart of accounts of the year",
    )
    warnings += _grouped(
        "unknown_series",
        unknown_series,
        "no document series {key}; its numbers are marked used, no counter rises",
    )
    rises = tuple(
        CounterRise(key, counters.last_used.get(key, 0), after)
        for key, after in sorted(last_used.items())
        if after != counters.last_used.get(key, 0)
    )
    return BookingsPlan(tuple(new), tuple(present), tuple(numbers), rises, tuple(warnings))


def _newest_first(precedents: list[Precedent]) -> list[Precedent]:
    # Stable: precedents of one date keep their order; those without a date go last.
    return sorted(precedents, key=lambda p: p.booking_date or date.min, reverse=True)


def merge_plan(
    plan: BookingsPlan, memory: SupplierMemory, counters: Counters
) -> tuple[SupplierMemory, Counters]:
    """The memory with the plan's new precedents and the counters with its numbers."""
    suppliers = {record.ico: record for record in memory.suppliers}
    added: defaultdict[str, list[Precedent]] = defaultdict(list)
    names: dict[str, str] = {}
    for booking in plan.new:
        added[booking.supplier_ico].append(booking.precedent)
        names.setdefault(booking.supplier_ico, booking.supplier_name)
    for ico, precedents in added.items():
        record = suppliers.get(ico)
        if record is None:
            suppliers[ico] = SupplierRecord(
                ico=ico, name=names[ico], precedents=_newest_first(precedents)
            )
        else:
            suppliers[ico] = record.model_copy(
                update={"precedents": _newest_first([*record.precedents, *precedents])}
            )
    last_used = dict(counters.last_used)
    for rise in plan.counters:
        last_used[rise.key] = max(last_used.get(rise.key, 0), rise.after)
    used = [*counters.used_numbers, *(n for n in plan.numbers if n not in counters.used_numbers)]
    return (
        memory.model_copy(update={"suppliers": list(suppliers.values())}),
        counters.model_copy(update={"last_used": last_used, "used_numbers": used}),
    )
