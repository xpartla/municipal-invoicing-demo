"""Reading and editing code lists (plan §6.2, §10.6, §10.9): the lists of a year, their entries
with a search insensitive to case and diacritics, the version history, the difference between
two versions, and the row edits.

A row edit (add, edit, deactivate, reactivate) makes a new version of the list and supersedes
the active one, in one transaction, audited. The editor sends the version it saw; when another
edit came first, that is a conflict. An edited version keeps its predecessor's source file and
reading warnings (most of its rows still come from there) and takes the edit's month as its
period.

A customer's lists need `customer.read` to read and `codelists.edit` to edit. The global lists
need `codelists.global` and are read-only here: they change by import (P2-M3).
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from riso.codelists.application.uow import CodelistsUnitOfWork
from riso.codelists.domain import (
    CUSTOMER_KINDS,
    GLOBAL_KINDS,
    CodeListVersion,
    Entry,
    ListKind,
    VersionInfo,
    VersionOrigin,
    VersionStatus,
    entry_fields,
    parse_entry,
)
from riso.codelists.domain.diff import diff_versions
from riso.identity import Permission
from riso.shared.clock import local_date
from riso.shared.context import RequestContext
from riso.shared.errors import Conflict, NotFound
from riso.text import fold

MAX_PAGE = 200


@dataclass(frozen=True, slots=True)
class VersionView:
    id: str
    kind: ListKind
    year: int
    number: int
    status: VersionStatus
    origin: VersionOrigin
    created_at: datetime
    created_by: str | None
    entry_count: int
    period: str | None
    note: str | None

    @classmethod
    def of(cls, info: VersionInfo) -> "VersionView":
        return cls(
            id=info.id,
            kind=info.kind,
            year=info.year,
            number=info.number,
            status=info.status,
            origin=info.origin,
            created_at=info.created_at,
            created_by=info.created_by,
            entry_count=info.entry_count,
            period=info.period,
            note=info.note,
        )


def entry_values(entry: Entry) -> dict[str, Any]:
    """The entry's fields as JSON values: amounts as numbers, tuples as lists."""
    values: dict[str, Any] = {}
    for name, value in asdict(entry).items():
        if isinstance(value, Decimal):
            values[name] = float(value)
        elif isinstance(value, tuple):
            values[name] = list(value)
        else:
            values[name] = value
    return values


@dataclass(frozen=True, slots=True)
class EntryView:
    key: str
    active: bool
    values: dict[str, Any]

    @classmethod
    def of(cls, entry: Entry) -> "EntryView":
        return cls(entry.key, entry.active, entry_values(entry))


@dataclass(frozen=True, slots=True)
class EntryPage:
    version: VersionView
    items: list[EntryView]
    total: int


@dataclass(frozen=True, slots=True)
class ListSummary:
    kind: ListKind
    fields: tuple[str, ...]
    version: VersionView | None
    """The active version; None while the list has none for the year."""


@dataclass(frozen=True, slots=True)
class ListsOverview:
    year: int
    years: list[int]
    """The years the owner has any list for."""
    lists: list[ListSummary]


@dataclass(frozen=True, slots=True)
class EntryChangeView:
    key: str
    before: EntryView
    after: EntryView


@dataclass(frozen=True, slots=True)
class DiffView:
    old: VersionView
    new: VersionView
    added: list[EntryView]
    removed: list[EntryView]
    changed: list[EntryChangeView]


def _require_read(ctx: RequestContext, customer_id: str | None) -> None:
    if customer_id is None:
        ctx.require(Permission.GLOBAL_CODELISTS)
    else:
        ctx.require(Permission.CUSTOMER_READ, customer_id)


def _check_kind(kind: ListKind, customer_id: str | None) -> None:
    if kind.is_global != (customer_id is None):
        owner = "global" if customer_id is None else "customer"
        raise NotFound(f"{kind} is not a {owner} list")


def lists_overview(
    ctx: RequestContext, uow: CodelistsUnitOfWork, customer_id: str | None, year: int
) -> ListsOverview:
    """Each list of the owner's with its active version for the year."""
    _require_read(ctx, customer_id)
    kinds = GLOBAL_KINDS if customer_id is None else CUSTOMER_KINDS
    with uow:
        lists = []
        for kind in kinds:
            version = uow.codelists.active(customer_id, kind, year)
            lists.append(
                ListSummary(
                    kind, entry_fields(kind), VersionView.of(version.info()) if version else None
                )
            )
        years = uow.codelists.years(customer_id)
    return ListsOverview(year, years, lists)


def _matches(entry: Entry, needle: str) -> bool:
    text = " ".join(
        [entry.key]
        + [str(v) for v in entry_values(entry).values() if isinstance(v, str)]
        + [str(a) for a in getattr(entry, "aliases", ())]
    )
    return needle in fold(text).casefold()


def _version(
    uow: CodelistsUnitOfWork,
    customer_id: str | None,
    kind: ListKind,
    year: int,
    version_id: str | None,
) -> CodeListVersion:
    if version_id is None:
        version = uow.codelists.active(customer_id, kind, year)
        if version is None:
            raise NotFound(f"no {kind} list for {year}")
        return version
    version = uow.codelists.get(customer_id, version_id)
    if version.kind is not kind:
        raise NotFound(f"no {kind} version {version_id}")
    return version


def list_entries(
    ctx: RequestContext,
    uow: CodelistsUnitOfWork,
    customer_id: str | None,
    kind: ListKind,
    year: int,
    *,
    version_id: str | None = None,
    query: str | None = None,
    active: bool | None = None,
    page: int = 1,
    size: int = 50,
) -> EntryPage:
    """A page of the list's entries in their order, the active version unless `version_id`
    names another. `query` matches the key and any text field (description, name, aliases)
    regardless of case and diacritics; `active` keeps only active or inactive rows."""
    _require_read(ctx, customer_id)
    _check_kind(kind, customer_id)
    size = max(1, min(size, MAX_PAGE))
    with uow:
        version = _version(uow, customer_id, kind, year, version_id)
    entries = list(version.entries)
    if active is not None:
        entries = [e for e in entries if e.active is active]
    needle = fold(query or "").casefold().strip()
    if needle:
        entries = [e for e in entries if _matches(e, needle)]
    start = (max(page, 1) - 1) * size
    return EntryPage(
        VersionView.of(version.info()),
        [EntryView.of(e) for e in entries[start : start + size]],
        len(entries),
    )


def list_versions(
    ctx: RequestContext,
    uow: CodelistsUnitOfWork,
    customer_id: str | None,
    kind: ListKind,
    year: int,
) -> list[VersionView]:
    """The list's versions for the year, the newest first."""
    _require_read(ctx, customer_id)
    _check_kind(kind, customer_id)
    with uow:
        return [VersionView.of(info) for info in uow.codelists.history(customer_id, kind, year)]


def version_difference(
    ctx: RequestContext,
    uow: CodelistsUnitOfWork,
    customer_id: str | None,
    kind: ListKind,
    old_id: str,
    new_id: str,
) -> DiffView:
    _require_read(ctx, customer_id)
    _check_kind(kind, customer_id)
    with uow:
        old = uow.codelists.get(customer_id, old_id)
        new = uow.codelists.get(customer_id, new_id)
    if old.kind is not kind or new.kind is not kind:
        raise NotFound(f"no {kind} versions {old_id}, {new_id}")
    try:
        diff = diff_versions(old, new)
    except ValueError as exc:
        raise NotFound(str(exc)) from exc
    return DiffView(
        old=VersionView.of(old.info()),
        new=VersionView.of(new.info()),
        added=[EntryView.of(e) for e in diff.added],
        removed=[EntryView.of(e) for e in diff.removed],
        changed=[
            EntryChangeView(c.key, EntryView.of(c.before), EntryView.of(c.after))
            for c in diff.changed
        ],
    )


# Row edits -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AddEntry:
    values: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class EditEntry:
    key: str
    values: Mapping[str, Any]
    """The fields to change; the others keep their values (the import's row numbers, the
    active flag)."""


@dataclass(frozen=True, slots=True)
class DeactivateEntry:
    key: str


@dataclass(frozen=True, slots=True)
class ReactivateEntry:
    key: str


Change = AddEntry | EditEntry | DeactivateEntry | ReactivateEntry

_ACTIONS: dict[type, str] = {
    AddEntry: "codelists.entry_added",
    EditEntry: "codelists.entry_edited",
    DeactivateEntry: "codelists.entry_deactivated",
    ReactivateEntry: "codelists.entry_reactivated",
}


def _apply(version: CodeListVersion, change: Change) -> tuple[tuple[Entry, ...], str, Entry | None]:
    """The successor's entries, the key edited and the entry before the edit."""
    kind = version.kind
    if isinstance(change, AddEntry):
        entry = parse_entry(kind, change.values)
        return version.with_added(entry), entry.key, None
    before = version.entry(change.key)
    if isinstance(change, EditEntry):
        current = {k: v for k, v in entry_values(before).items() if k in entry_fields(kind)}
        entry = parse_entry(kind, {**current, **change.values})
        return version.with_replaced(change.key, entry), entry.key, before
    if isinstance(change, DeactivateEntry):
        return version.with_deactivated(change.key), change.key, before
    return version.with_reactivated(change.key), change.key, before


def edit_list(
    ctx: RequestContext,
    uow: CodelistsUnitOfWork,
    customer_id: str,
    kind: ListKind,
    year: int,
    change: Change,
    *,
    version_id: str | None,
) -> VersionView:
    """Applies one row edit as a new version of the customer's list. `version_id` is the
    active version the editor saw (None when the list has none for the year yet, which only
    an addition may start)."""
    ctx.require(Permission.CODELISTS_EDIT, customer_id)
    _check_kind(kind, customer_id)
    with uow:
        now = uow.clock.now()
        period = local_date(now).strftime("%Y-%m")
        current = uow.codelists.active(customer_id, kind, year)
        if current is None:
            if version_id is not None or not isinstance(change, AddEntry):
                raise NotFound(f"no {kind} list for {year}")
            entry = parse_entry(kind, change.values)
            successor = CodeListVersion.first(
                uow.ids.new(),
                kind,
                customer_id,
                year,
                [entry],
                origin=VersionOrigin.EDIT,
                at=now,
                actor=ctx.actor_id,
                period=period,
            )
            key, before = entry.key, None
        else:
            if version_id != current.id:
                raise Conflict(f"{kind} {year} is at version {current.number}; reload it")
            entries, key, before = _apply(current, change)
            successor = current.succeed(
                uow.ids.new(),
                entries,
                origin=VersionOrigin.EDIT,
                at=now,
                actor=ctx.actor_id,
                period=period,
                source=current.source,
                warnings=current.warnings,
            )
            uow.codelists.save(current)
        uow.codelists.add(successor)
        after = next((e for e in successor.entries if e.key == key), None)
        uow.audit.record(
            ctx,
            _ACTIONS[type(change)],
            target_type="codelist_version",
            target_id=successor.id,
            customer_id=customer_id,
            details={
                "kind": kind.value,
                "year": year,
                "number": successor.number,
                "key": key,
                "before": entry_values(before) if before else None,
                "after": entry_values(after) if after else None,
            },
        )
        uow.commit()
    return VersionView.of(successor.info())


# The global lists' yearly checklist ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChecklistYear:
    year: int
    lists: list[ListSummary]

    @property
    def complete(self) -> bool:
        return all(summary.version is not None for summary in self.lists)


def global_checklist(
    ctx: RequestContext, uow: CodelistsUnitOfWork, *, this_year: int
) -> list[ChecklistYear]:
    """Which global lists exist for each year: every year that has one, and this year and
    the next, so a missing year shows (plan §6.1)."""
    ctx.require(Permission.GLOBAL_CODELISTS)
    with uow:
        years = sorted(set(uow.codelists.years(None)) | {this_year, this_year + 1})
        found = []
        for year in years:
            lists = []
            for kind in GLOBAL_KINDS:
                version = uow.codelists.active(None, kind, year)
                lists.append(
                    ListSummary(
                        kind,
                        entry_fields(kind),
                        VersionView.of(version.info()) if version else None,
                    )
                )
            found.append(ChecklistYear(year, lists))
    return found


__all__ = [
    "AddEntry",
    "ChecklistYear",
    "DeactivateEntry",
    "DiffView",
    "EditEntry",
    "EntryChangeView",
    "EntryPage",
    "EntryView",
    "ListSummary",
    "ListsOverview",
    "ReactivateEntry",
    "VersionView",
    "edit_list",
    "entry_values",
    "global_checklist",
    "list_entries",
    "list_versions",
    "lists_overview",
    "version_difference",
]
