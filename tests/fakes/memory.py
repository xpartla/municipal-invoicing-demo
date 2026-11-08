"""A base for in-memory repositories that behave like the SQL ones: they hand out copies, so
a change counts only once it is saved, and a rollback restores what was there when the unit
of work began."""

import copy
from typing import Any


class SnapshotStore:
    def __init__(self) -> None:
        self.rows: dict[Any, Any] = {}
        self._snapshot: dict[Any, Any] | None = None

    def begin(self) -> None:
        self._snapshot = copy.deepcopy(self.rows)

    def rollback(self) -> None:
        if self._snapshot is not None:
            self.rows = self._snapshot
        self._snapshot = None

    def commit(self) -> None:
        self._snapshot = None

    def put(self, key: Any, value: Any) -> None:
        self.rows[key] = copy.deepcopy(value)

    def take(self, key: Any) -> Any:
        return copy.deepcopy(self.rows[key])

    def values(self) -> list[Any]:
        return [copy.deepcopy(v) for v in self.rows.values()]
