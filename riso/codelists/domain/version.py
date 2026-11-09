"""The `CodeListVersion` aggregate (plan §6.2): an immutable snapshot of one list for one year.

A version has a kind, an owner (a customer, or none for a global list), a year and a number
counted from 1 per kind, owner and year. Every import and every row edit makes a new version
that supersedes the active one; old versions stay readable. Only the status of a version
ever changes, from active to superseded.

The source and the warnings record where the entries came from (the exported file and what
reading it noticed), so the reference bundle built from the versions says what the
committed bundle says. The period is the month the data describes: the export's for a seeded
or imported list, the edit's for an edited one.
"""

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime

from riso.codelists.domain.entries import ENTRY_TYPES, Entry, deactivated
from riso.codelists.domain.kinds import ListKind, VersionOrigin, VersionStatus
from riso.shared.errors import Conflict, InvalidState, NotFound, ValidationFailed
from riso.shared.events import DomainEvent

MIN_YEAR, MAX_YEAR = 2000, 2100
_PERIOD = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


@dataclass(frozen=True, slots=True)
class SourceRef:
    """The file a version's entries were read from."""

    name: str
    sha256: str
    data_rows: int


@dataclass(frozen=True, slots=True)
class ListWarning:
    """Something reading the source noticed: a duplicate key merged, missing descriptions."""

    code: str
    source: str
    rows: tuple[int, ...]
    message: str


@dataclass(frozen=True, slots=True)
class CodeListVersionCreated(DomainEvent):
    version_id: str
    kind: ListKind
    customer_id: str | None
    year: int
    number: int
    origin: VersionOrigin
    superseded_id: str | None


@dataclass(frozen=True, slots=True)
class VersionInfo:
    """A version without its entries, as the history lists it."""

    id: str
    kind: ListKind
    customer_id: str | None
    year: int
    number: int
    status: VersionStatus
    origin: VersionOrigin
    created_at: datetime
    created_by: str | None
    entry_count: int
    period: str | None = None
    import_run_id: str | None = None
    note: str | None = None


def _check_owner(kind: ListKind, customer_id: str | None) -> None:
    if kind.is_global and customer_id is not None:
        raise InvalidState(f"{kind} is a global list; it has no customer")
    if not kind.is_global and customer_id is None:
        raise InvalidState(f"{kind} is a customer's list; it needs the customer")


def _check_year(year: int) -> None:
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValidationFailed.on("year", f"between {MIN_YEAR} and {MAX_YEAR}", "year")


def _check_period(period: str | None) -> None:
    if period is not None and not _PERIOD.fullmatch(period):
        raise ValidationFailed.on("period", "YYYY-MM", "period")


def _check_entries(kind: ListKind, entries: tuple[Entry, ...]) -> None:
    expected = ENTRY_TYPES[kind]
    wrong = [type(e).__name__ for e in entries if not isinstance(e, expected)]
    if wrong:
        raise InvalidState(f"{kind} holds {expected.__name__}, not {sorted(set(wrong))}")
    repeated = sorted(key for key, count in Counter(e.key for e in entries).items() if count > 1)
    if repeated:
        raise Conflict(f"{kind} repeats keys {repeated[:5]}")


@dataclass(slots=True)
class CodeListVersion:
    id: str
    kind: ListKind
    customer_id: str | None
    year: int
    number: int
    status: VersionStatus
    origin: VersionOrigin
    created_at: datetime
    created_by: str | None
    entries: tuple[Entry, ...]
    period: str | None = None
    source: SourceRef | None = None
    warnings: tuple[ListWarning, ...] = ()
    import_run_id: str | None = None
    note: str | None = None
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        _check_owner(self.kind, self.customer_id)
        _check_year(self.year)
        _check_period(self.period)
        if self.number < 1:
            raise InvalidState("version numbers start at 1")
        _check_entries(self.kind, self.entries)

    @classmethod
    def first(
        cls,
        version_id: str,
        kind: ListKind,
        customer_id: str | None,
        year: int,
        entries: Iterable[Entry],
        *,
        origin: VersionOrigin,
        at: datetime,
        actor: str | None,
        period: str | None = None,
        source: SourceRef | None = None,
        warnings: Iterable[ListWarning] = (),
        import_run_id: str | None = None,
        note: str | None = None,
    ) -> "CodeListVersion":
        """Version 1 of a list that has none for the year."""
        version = cls(
            id=version_id,
            kind=kind,
            customer_id=customer_id,
            year=year,
            number=1,
            status=VersionStatus.ACTIVE,
            origin=origin,
            created_at=at,
            created_by=actor,
            entries=tuple(entries),
            period=period,
            source=source,
            warnings=tuple(warnings),
            import_run_id=import_run_id,
            note=note,
        )
        version._created(None)
        return version

    def succeed(
        self,
        version_id: str,
        entries: Iterable[Entry],
        *,
        origin: VersionOrigin,
        at: datetime,
        actor: str | None,
        period: str | None = None,
        source: SourceRef | None = None,
        warnings: Iterable[ListWarning] = (),
        import_run_id: str | None = None,
        note: str | None = None,
    ) -> "CodeListVersion":
        """The next version of this list, which supersedes this one. Only the active
        version has a successor."""
        if self.status is not VersionStatus.ACTIVE:
            raise InvalidState(f"version {self.id} is superseded; edit the active one")
        successor = CodeListVersion(
            id=version_id,
            kind=self.kind,
            customer_id=self.customer_id,
            year=self.year,
            number=self.number + 1,
            status=VersionStatus.ACTIVE,
            origin=origin,
            created_at=at,
            created_by=actor,
            entries=tuple(entries),
            period=period,
            source=source,
            warnings=tuple(warnings),
            import_run_id=import_run_id,
            note=note,
        )
        self.status = VersionStatus.SUPERSEDED
        successor._created(self.id)
        return successor

    def _created(self, superseded_id: str | None) -> None:
        self.events.append(
            CodeListVersionCreated(
                self.id,
                self.kind,
                self.customer_id,
                self.year,
                self.number,
                self.origin,
                superseded_id,
            )
        )

    @property
    def active(self) -> bool:
        return self.status is VersionStatus.ACTIVE

    def entry(self, key: str) -> Entry:
        for entry in self.entries:
            if entry.key == key:
                return entry
        raise NotFound(f"no entry {key!r} in version {self.id}")

    def active_entries(self) -> tuple[Entry, ...]:
        """What the engine and the validation see: inactive rows left out."""
        return tuple(e for e in self.entries if e.active)

    def info(self) -> VersionInfo:
        return VersionInfo(
            id=self.id,
            kind=self.kind,
            customer_id=self.customer_id,
            year=self.year,
            number=self.number,
            status=self.status,
            origin=self.origin,
            created_at=self.created_at,
            created_by=self.created_by,
            entry_count=len(self.entries),
            period=self.period,
            import_run_id=self.import_run_id,
            note=self.note,
        )

    # Row edits: each returns the entries of the successor; the use case makes it.

    def with_added(self, entry: Entry) -> tuple[Entry, ...]:
        if any(e.key == entry.key for e in self.entries):
            raise Conflict(f"{self.kind} already has {entry.key!r}")
        result = (*self.entries, entry)
        _check_entries(self.kind, result)
        return result

    def with_replaced(self, key: str, entry: Entry) -> tuple[Entry, ...]:
        """The entry at `key` replaced; the new one may have another key, if that is free."""
        self.entry(key)
        if entry.key != key and any(e.key == entry.key for e in self.entries):
            raise Conflict(f"{self.kind} already has {entry.key!r}")
        result = tuple(entry if e.key == key else e for e in self.entries)
        _check_entries(self.kind, result)
        return result

    def with_deactivated(self, key: str) -> tuple[Entry, ...]:
        if not self.entry(key).active:
            raise InvalidState(f"{key!r} is already inactive")
        return tuple(deactivated(e) if e.key == key else e for e in self.entries)

    def with_reactivated(self, key: str) -> tuple[Entry, ...]:
        if self.entry(key).active:
            raise InvalidState(f"{key!r} is already active")
        return tuple(replace(e, active=True) if e.key == key else e for e in self.entries)
