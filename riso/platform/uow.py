"""The SQLAlchemy unit of work. Context units of work subclass it and add their
repositories, built on `self.session` in `_start()`."""

from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session

from riso.platform.db import Database
from riso.shared.clock import Clock
from riso.shared.events import DomainEvent, EventDispatcher, HasEvents
from riso.shared.ids import IdGenerator


class SqlUnitOfWork:
    """One transaction. `commit()` collects the tracked aggregates' events, commits, and only
    then dispatches them; leaving the block without a commit, or with an exception, rolls
    back and drops the events.

    On SQLite the transaction begins with BEGIN IMMEDIATE unless `immediate=False`. A command
    reads before it writes; a deferred transaction that read an older snapshot cannot become
    a writer once another connection has committed, and SQLite then fails at once with
    "database is locked" instead of waiting. Taking the write lock up front makes writers
    queue for it (up to the busy timeout). Read-only work passes `immediate=False`.
    """

    session: Session

    def __init__(
        self,
        db: Database,
        *,
        clock: Clock,
        ids: IdGenerator,
        dispatcher: EventDispatcher | None = None,
        immediate: bool = True,
    ) -> None:
        self._db = db
        self.clock = clock
        self.ids = ids
        self._dispatcher = dispatcher or EventDispatcher()
        self._immediate = immediate
        self._tracked: list[HasEvents] = []

    def __enter__(self) -> Self:
        self.session = self._db.session(immediate=self._immediate)
        self._tracked = []
        self._start()
        return self

    def _start(self) -> None:
        """Hook for subclasses: create the repositories on `self.session`."""

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            self.rollback()  # a no-op after a commit
        finally:
            self.session.close()

    def track(self, aggregate: HasEvents) -> None:
        if not any(tracked is aggregate for tracked in self._tracked):
            self._tracked.append(aggregate)

    def commit(self) -> None:
        events: list[DomainEvent] = [e for a in self._tracked for e in a.events]
        self.session.commit()
        self._forget_events()
        self._dispatcher.dispatch(events)

    def rollback(self) -> None:
        self.session.rollback()
        self._forget_events()

    def _forget_events(self) -> None:
        for aggregate in self._tracked:
            aggregate.events.clear()
        self._tracked.clear()
