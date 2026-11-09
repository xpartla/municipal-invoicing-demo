"""The difference between two versions of a list (plan §6.2, §10.6): entries added, removed
and changed, matched by key. A row whose only change is its position is not a change, nor
one whose only change is the file rows it was read from (`row`, `rows`): an import of the
same list from another file changes nothing."""

from dataclasses import dataclass, replace

from riso.codelists.domain.entries import AccountEntry, BudgetEntry, Entry
from riso.codelists.domain.version import CodeListVersion


@dataclass(frozen=True, slots=True)
class EntryChange:
    key: str
    before: Entry
    after: Entry


@dataclass(frozen=True, slots=True)
class VersionDiff:
    added: tuple[Entry, ...]
    removed: tuple[Entry, ...]
    changed: tuple[EntryChange, ...]

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


def _content(entry: Entry) -> Entry:
    """The entry without where it was read from."""
    if isinstance(entry, AccountEntry):
        return replace(entry, row=None)
    if isinstance(entry, BudgetEntry):
        return replace(entry, rows=())
    return entry


def diff_versions(old: CodeListVersion, new: CodeListVersion) -> VersionDiff:
    """What changed from `old` to `new`, both of the same list (kind, owner and year), in the
    order of `new` (removed entries in the order of `old`)."""
    if (old.kind, old.customer_id, old.year) != (new.kind, new.customer_id, new.year):
        raise ValueError(f"versions {old.id} and {new.id} are not of the same list")
    before = {e.key: e for e in old.entries}
    after = {e.key: e for e in new.entries}
    return VersionDiff(
        added=tuple(e for e in new.entries if e.key not in before),
        removed=tuple(e for e in old.entries if e.key not in after),
        changed=tuple(
            EntryChange(e.key, before[e.key], e)
            for e in new.entries
            if e.key in before and _content(before[e.key]) != _content(e)
        ),
    )
