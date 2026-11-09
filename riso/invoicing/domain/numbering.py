"""Document numbers per customer, series and year (plan §7.2, §2 decisions 61 and 62).

A `NumberSeries` (FD in 2026, say) has a counter, `last_used`, and the numbers held in it.
Every number is held at most once:

- by a **booked** invoice; it moves when a booking makes room, unless the invoice has been
  exported or paid (then it is *frozen*);
- by a **reserved** invoice: one that was unbooked while its number was not the series'
  last keeps the number for when it is booked again; it moves like a booked one;
- by an **external** booking: a number from imported past bookings or the initial state,
  with no invoice in riso. It never moves.

Booking places the invoice (`place`):

- with a handwritten number N (or one the user typed): N if it is free. If it is held, the
  one of the two supplied earlier keeps N (an external holder always does) and the other
  goes to N + 1;
- without one: by its date of supply, right after the last holder supplied on or before
  it; before every dated holder when none is, and after the counter when there is none.

From the place it gets, the holders on the following consecutive numbers move up by one,
as far as the first free number. A move that would reach a frozen or external holder
refuses the booking (`NumberFrozen`), so the user sets the number by hand.

Ties on the date of supply go to the earlier upload, then to the lower invoice ID.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from enum import StrEnum

from riso.reference import format_number, parse_number
from riso.shared.errors import Conflict, ValidationFailed
from riso.shared.events import DomainEvent

_EARLIEST = datetime.min.replace(tzinfo=UTC)


class HolderKind(StrEnum):
    BOOKED = "booked"
    RESERVED = "reserved"
    EXTERNAL = "external"


OrderKey = tuple[date, datetime, str]


@dataclass(frozen=True, slots=True)
class Holder:
    """A number held in a series."""

    id: str
    sequence: int
    kind: HolderKind
    invoice_id: str | None = None
    supply_date: date | None = None
    received_at: datetime | None = None
    frozen: bool = False
    """An exported or paid invoice's number; external numbers are always frozen."""

    @property
    def movable(self) -> bool:
        return self.kind is not HolderKind.EXTERNAL and not self.frozen

    @property
    def key(self) -> OrderKey:
        """External holders, without a date, sort before everything."""
        return (
            self.supply_date or date.min,
            self.received_at or _EARLIEST,
            self.invoice_id or "",
        )


@dataclass(frozen=True, slots=True)
class Newcomer:
    """The invoice being booked."""

    invoice_id: str
    supply_date: date
    received_at: datetime
    sequence: int | None = None
    """The handwritten (or typed) number's sequence; None places the invoice by date."""

    @property
    def key(self) -> OrderKey:
        return (self.supply_date, self.received_at, self.invoice_id)


class NumberFrozen(Conflict):
    """A booking's shift would move a number that never moves."""

    def __init__(self, number: str, holder: Holder) -> None:
        what = "an imported booking's" if holder.kind is HolderKind.EXTERNAL else "exported"
        super().__init__(f"{number} is {what}; a booking cannot move it, set the number by hand")
        self.number = number
        self.holder = holder


def numberable(pattern: str) -> bool:
    """Whether a series of the pattern can be numbered by a counter per year: a pattern
    that numbers per month (bank statements, `BU1/MM-RR/XXX`) is not."""
    try:
        format_number(pattern, 1, 2000)
    except ValueError:
        return False
    return True


def place(
    holders: Iterable[Holder], newcomer: Newcomer, last_used: int
) -> tuple[int, tuple[Holder, ...]]:
    """The newcomer's sequence and the holders that move up by one, lowest first. A holder
    of the newcomer itself (its reservation) is left out. Raises `NumberFrozen` (with the
    sequence as its number) when a frozen holder would have to move."""
    taken = {h.sequence: h for h in holders if h.invoice_id != newcomer.invoice_id}
    if newcomer.sequence is not None:
        start = newcomer.sequence
        holder = taken.get(start)
        if holder is not None and holder.key <= newcomer.key:
            start += 1
    else:
        dated = [h for h in taken.values() if h.supply_date is not None]
        before = [h.sequence for h in dated if h.key <= newcomer.key]
        if before:
            start = max(before) + 1
        elif dated:
            start = min(h.sequence for h in dated)
        else:
            start = max(last_used, max(taken, default=0)) + 1
    moving: list[Holder] = []
    sequence = start
    while (holder := taken.get(sequence)) is not None:
        if not holder.movable:
            raise NumberFrozen(str(sequence), holder)
        moving.append(holder)
        sequence += 1
    return start, tuple(moving)


@dataclass(frozen=True, slots=True)
class Renumbering:
    """A holder the booking moves up by one."""

    invoice_id: str | None
    kind: HolderKind
    old: str
    new: str


@dataclass(frozen=True, slots=True)
class Placement:
    """Where a booking goes in its series, and what moves to make room."""

    series: str
    year: int
    sequence: int
    number: str
    requested: str | None
    """The handwritten or typed number asked for; None when placed by date."""
    shifts: tuple[Renumbering, ...] = ()

    @property
    def moved(self) -> bool:
        """Whether the booking did not get the number it asked for."""
        return self.requested is not None and self.requested != self.number


class Release(StrEnum):
    """What unbooking did to the invoice's number (decision 62)."""

    RELEASED = "released"
    """It was the series' last: the counter stepped back."""
    RESERVED = "reserved"
    """It stays the invoice's for when it is booked again."""
    NONE = "none"


@dataclass(slots=True)
class NumberSeries:
    id: str
    customer_id: str
    series: str
    year: int
    pattern: str
    """The document series' pattern, e.g. `FD/XXX/RR`."""
    last_used: int
    updated_at: datetime
    holders: list[Holder] = field(default_factory=list)
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def new(
        cls,
        series_id: str,
        customer_id: str,
        series: str,
        year: int,
        pattern: str,
        at: datetime,
        *,
        last_used: int = 0,
    ) -> "NumberSeries":
        if last_used < 0:
            raise ValidationFailed.on("last_used", "the counter cannot be negative")
        if not numberable(pattern):
            raise ValidationFailed.on("pattern", f"{pattern} is numbered per month, not per year")
        return cls(series_id, customer_id, series, year, pattern, last_used, at)

    @property
    def key(self) -> str:
        """`<series>/<year>`, as the engine's counters name it."""
        return f"{self.series}/{self.year}"

    @property
    def highest(self) -> int:
        return max((h.sequence for h in self.holders), default=0)

    def number(self, sequence: int) -> str:
        return format_number(self.pattern, sequence, self.year)

    def sequence_of(self, number: str) -> int | None:
        """The sequence of a number written in this series and year, else None."""
        parsed = parse_number(self.pattern, number)
        if parsed is None or (parsed.year is not None and parsed.year != self.year % 100):
            return None
        return parsed.sequence

    def holder_at(self, sequence: int) -> Holder | None:
        return next((h for h in self.holders if h.sequence == sequence), None)

    def holder_of(self, invoice_id: str) -> Holder | None:
        return next((h for h in self.holders if h.invoice_id == invoice_id), None)

    def gaps(self) -> list[int]:
        """Free numbers between the lowest and the highest held."""
        held = {h.sequence for h in self.holders}
        if not held:
            return []
        return [n for n in range(min(held), max(held)) if n not in held]

    # Booking

    def _place(self, newcomer: Newcomer) -> tuple[int, tuple[Holder, ...]]:
        try:
            return place(self.holders, newcomer, self.last_used)
        except NumberFrozen as exc:
            raise NumberFrozen(self.number(exc.holder.sequence), exc.holder) from None

    def preview(self, newcomer: Newcomer, *, requested: str | None = None) -> Placement:
        """Where booking the newcomer would put it. Raises `NumberFrozen`."""
        sequence, moving = self._place(newcomer)
        return self._placement(sequence, moving, requested)

    def _placement(
        self, sequence: int, moving: tuple[Holder, ...], requested: str | None
    ) -> Placement:
        return Placement(
            self.series,
            self.year,
            sequence,
            self.number(sequence),
            requested,
            tuple(
                Renumbering(
                    h.invoice_id, h.kind, self.number(h.sequence), self.number(h.sequence + 1)
                )
                for h in moving
            ),
        )

    def allocate(
        self, newcomer: Newcomer, holder_id: str, at: datetime, *, requested: str | None = None
    ) -> Placement:
        """Books the newcomer's number: its own reservation goes, the following holders move
        up, and the counter rises to the highest number held."""
        sequence, moving = self._place(newcomer)
        placement = self._placement(sequence, moving, requested)
        moved = {h.id for h in moving}
        kept = [h for h in self.holders if h.invoice_id != newcomer.invoice_id]
        self.holders = [replace(h, sequence=h.sequence + 1) if h.id in moved else h for h in kept]
        self.holders.append(
            Holder(
                holder_id,
                placement.sequence,
                HolderKind.BOOKED,
                newcomer.invoice_id,
                newcomer.supply_date,
                newcomer.received_at,
            )
        )
        self.last_used = max(self.last_used, self.highest)
        self.updated_at = at
        return placement

    def release(self, invoice_id: str, at: datetime) -> Release:
        """Unbooking (decision 62): the series' last number is freed and the counter steps
        back; any other stays reserved for the invoice."""
        holder = self.holder_of(invoice_id)
        if holder is None or holder.kind is not HolderKind.BOOKED:
            return Release.NONE
        self.updated_at = at
        if holder.sequence == self.last_used:
            self.holders.remove(holder)
            self.last_used -= 1
            return Release.RELEASED
        self.holders[self.holders.index(holder)] = replace(holder, kind=HolderKind.RESERVED)
        return Release.RESERVED

    def drop_reservation(self, invoice_id: str, at: datetime) -> bool:
        """The invoice was discarded, or is booked into another series."""
        holder = self.holder_of(invoice_id)
        if holder is None or holder.kind is not HolderKind.RESERVED:
            return False
        self.holders.remove(holder)
        self.updated_at = at
        return True

    def freeze(self, invoice_id: str, at: datetime) -> bool:
        """The invoice was exported or paid: its number never moves again."""
        holder = self.holder_of(invoice_id)
        if holder is None or holder.frozen:
            return False
        self.holders[self.holders.index(holder)] = replace(holder, frozen=True)
        self.updated_at = at
        return True

    # The counter and external numbers

    def mark_external(self, sequence: int, holder_id: str, at: datetime) -> bool:
        """A number used outside riso (past bookings, the initial state). False when it is
        held already."""
        if sequence < 1:
            raise ValidationFailed.on("number", "a document number starts at 1")
        if self.holder_at(sequence) is not None:
            return False
        self.holders.append(Holder(holder_id, sequence, HolderKind.EXTERNAL, frozen=True))
        self.last_used = max(self.last_used, sequence)
        self.updated_at = at
        return True

    def raise_counter(self, value: int, at: datetime) -> None:
        if value > self.last_used:
            self.last_used, self.updated_at = value, at

    def set_last_used(self, value: int, at: datetime) -> int:
        """The audited edit under Systém (plan §7.2), until the counter syncs with TOPSET.
        It cannot go below a number held. Returns the old value."""
        if value < 0:
            raise ValidationFailed.on("last_used", "the counter cannot be negative")
        if value < self.highest:
            raise ValidationFailed.on(
                "last_used",
                f"{self.number(self.highest)} is used; the counter cannot go below it",
                "below_used",
            )
        old, self.last_used, self.updated_at = self.last_used, value, at
        return old
