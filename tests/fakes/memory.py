"""A base for in-memory repositories that behave like the SQL ones: they hand out copies, so
a change counts only once it is saved, and a rollback restores what was there when the unit
of work began."""

import copy
from types import TracebackType
from typing import Any, Self, TypeVar

from tests.fakes.uow import InMemoryUnitOfWork


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


S = TypeVar("S", bound=SnapshotStore)


class StoresUnitOfWork(InMemoryUnitOfWork):
    """An in-memory unit of work over snapshot stores: entering snapshots them, leaving
    without a commit restores them."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._stores: list[SnapshotStore] = []

    def store(self, store: S) -> S:
        self._stores.append(store)
        return store

    def __enter__(self) -> Self:
        super().__enter__()
        for store in self._stores:
            store.begin()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        for store in self._stores:
            store.rollback()  # restores the snapshot unless the work was committed
        super().__exit__(exc_type, exc, tb)

    def commit(self) -> None:
        for store in self._stores:
            store.commit()
        super().commit()

    def rollback(self) -> None:
        for store in self._stores:
            store.rollback()
        super().rollback()
