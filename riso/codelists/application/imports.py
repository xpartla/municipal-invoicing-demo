"""What the import tool (the exchange context) asks of the code lists (plan §9.2 steps 3–4):
check a list of candidate entries, and make them the list's new version.

Both run inside the caller's unit of work, so applying an import (the new version, the run's
new state and the audit entry) commits once.

The check parses each candidate through the entry's contract (a failure is a problem with
the candidate's rows), validates the new list against the year's global lists (plan §6.3),
and compares it with the active version. Applying refuses candidates with problems, and
refuses when the active version is no longer the one the dry run compared with.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from riso.codelists.application.checks import global_lists
from riso.codelists.application.lists import EntryChangeView, EntryView, VersionView
from riso.codelists.application.uow import CodelistsUnitOfWork
from riso.codelists.domain import (
    CodeListVersion,
    Entry,
    ListKind,
    ListWarning,
    SourceRef,
    VersionOrigin,
    parse_entry,
    validate_list,
)
from riso.codelists.domain.diff import diff_versions
from riso.identity import Permission
from riso.shared.context import RequestContext
from riso.shared.errors import Conflict, InvalidState, NotFound, ValidationFailed


@dataclass(frozen=True, slots=True)
class CandidateEntry:
    """One entry an import proposes: its fields as the entry parser takes them, and the
    file rows it comes from."""

    key: str
    rows: tuple[int, ...]
    values: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class EntryProblem:
    key: str
    rows: tuple[int, ...]
    field: str | None
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ListFinding:
    """A finding against the global lists: `error` or `warning`."""

    severity: str
    code: str
    key: str | None
    field: str | None
    value: str | None
    message: str


@dataclass(frozen=True, slots=True)
class ImportSource:
    name: str
    sha256: str
    data_rows: int


@dataclass(frozen=True, slots=True)
class ImportWarning:
    code: str
    source: str
    rows: tuple[int, ...]
    message: str


@dataclass(frozen=True, slots=True)
class ImportCheck:
    entries: tuple[EntryView, ...]
    """The candidates that parsed, in their order."""
    problems: tuple[EntryProblem, ...]
    findings: tuple[ListFinding, ...]
    active: VersionView | None
    added: tuple[EntryView, ...]
    removed: tuple[EntryView, ...]
    changed: tuple[EntryChangeView, ...]

    @property
    def removed_keys(self) -> frozenset[str]:
        return frozenset(e.key for e in self.removed)

    @property
    def unchanged(self) -> int:
        return len(self.entries) - len(self.added) - len(self.changed)


def _kind(kind: str, customer_id: str | None) -> ListKind:
    try:
        found = ListKind(kind)
    except ValueError:
        raise NotFound(f"no code list kind {kind!r}") from None
    if found.is_global != (customer_id is None):
        raise NotFound(f"{found} is not a {'global' if customer_id is None else 'customer'} list")
    return found


def _parse(
    kind: ListKind, candidates: Iterable[CandidateEntry]
) -> tuple[list[Entry], list[EntryProblem]]:
    entries: list[Entry] = []
    problems: list[EntryProblem] = []
    seen: dict[str, tuple[int, ...]] = {}
    for candidate in candidates:
        try:
            entry = parse_entry(kind, candidate.values)
        except ValidationFailed as exc:
            problems += [
                EntryProblem(candidate.key, candidate.rows, e.field or None, e.code, e.message)
                for e in exc.errors or []
            ] or [EntryProblem(candidate.key, candidate.rows, None, "invalid", exc.message)]
            continue
        if entry.key in seen:
            problems.append(
                EntryProblem(
                    entry.key,
                    candidate.rows,
                    None,
                    "duplicate_key",
                    f"{entry.key} repeats rows {list(seen[entry.key])}",
                )
            )
            continue
        seen[entry.key] = candidate.rows
        entries.append(entry)
    return entries, problems


def _candidate(
    uow: CodelistsUnitOfWork,
    kind: ListKind,
    customer_id: str | None,
    year: int,
    entries: Sequence[Entry],
) -> CodeListVersion:
    return CodeListVersion.first(
        "candidate",
        kind,
        customer_id,
        year,
        entries,
        origin=VersionOrigin.IMPORT,
        at=uow.clock.now(),
        actor=None,
    )


def check_import(
    uow: CodelistsUnitOfWork,
    customer_id: str | None,
    kind: str,
    year: int,
    candidates: Iterable[CandidateEntry],
) -> ImportCheck:
    """The candidates checked against the contracts, the global lists of the year and the
    active version. Call inside the unit of work; it writes nothing."""
    list_kind = _kind(kind, customer_id)
    entries, problems = _parse(list_kind, candidates)
    candidate = _candidate(uow, list_kind, customer_id, year, entries)
    active = uow.codelists.active(customer_id, list_kind, year)
    findings: list[ListFinding] = []
    if customer_id is not None:
        findings = [
            ListFinding(f.severity.value, f.code.value, f.key, f.field, f.value, f.message)
            for f in validate_list(candidate, global_lists(uow, year))
        ]
    if active is None:
        added, removed, changed = list(candidate.entries), [], []
    else:
        diff = diff_versions(active, candidate)
        added, removed, changed = list(diff.added), list(diff.removed), list(diff.changed)
    return ImportCheck(
        entries=tuple(EntryView.of(e) for e in entries),
        problems=tuple(problems),
        findings=tuple(findings),
        active=VersionView.of(active.info()) if active else None,
        added=tuple(EntryView.of(e) for e in added),
        removed=tuple(EntryView.of(e) for e in removed),
        changed=tuple(
            EntryChangeView(c.key, EntryView.of(c.before), EntryView.of(c.after)) for c in changed
        ),
    )


def active_entries(
    uow: CodelistsUnitOfWork, customer_id: str | None, kind: str, year: int
) -> tuple[EntryView, ...]:
    """The entries of the list's active version for the year (none without one). Call inside
    the unit of work."""
    active = uow.codelists.active(customer_id, _kind(kind, customer_id), year)
    return tuple(EntryView.of(e) for e in active.entries) if active else ()


def apply_import(
    ctx: RequestContext,
    uow: CodelistsUnitOfWork,
    customer_id: str | None,
    kind: str,
    year: int,
    candidates: Iterable[CandidateEntry],
    *,
    expected_version_id: str | None,
    import_run_id: str,
    source: ImportSource,
    warnings: Iterable[ImportWarning] = (),
    period: str | None = None,
) -> VersionView:
    """The candidates as the list's new version, superseding the active one. Call inside the
    unit of work; the caller commits (and audits). Raises `Conflict` when the active version
    is not `expected_version_id`, `InvalidState` when a candidate has a problem."""
    if customer_id is None:
        ctx.require(Permission.GLOBAL_CODELISTS)
    else:
        ctx.require(Permission.CODELISTS_EDIT, customer_id)
    list_kind = _kind(kind, customer_id)
    entries, problems = _parse(list_kind, candidates)
    if problems:
        raise InvalidState(f"{len(problems)} entries of the import do not parse")
    active = uow.codelists.active(customer_id, list_kind, year)
    if (active.id if active else None) != expected_version_id:
        raise Conflict(f"{list_kind} {year} changed since the dry run")
    now = uow.clock.now()
    details: dict[str, Any] = {
        "origin": VersionOrigin.IMPORT,
        "at": now,
        "actor": ctx.actor_id,
        "period": period,
        "source": SourceRef(source.name, source.sha256, source.data_rows),
        "warnings": [ListWarning(w.code, w.source, w.rows, w.message) for w in warnings],
        "import_run_id": import_run_id,
        "note": f"import of {source.name}",
    }
    if active is None:
        version = CodeListVersion.first(
            uow.ids.new(), list_kind, customer_id, year, entries, **details
        )
    else:
        version = active.succeed(uow.ids.new(), entries, **details)
        uow.codelists.save(active)
    uow.codelists.add(version)
    return VersionView.of(version.info())
