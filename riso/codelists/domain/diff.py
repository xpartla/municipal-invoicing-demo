"""The difference between two versions of a list (plan §6.2, §10.6): entries added, removed
and changed, matched by key. A row whose only change is its position is not a change."""

from dataclasses import dataclass

from riso.codelists.domain.entries import Entry
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
            if e.key in before and before[e.key] != e
        ),
    )
