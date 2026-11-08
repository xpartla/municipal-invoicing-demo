"""An in-memory unit of work for application tests. Contexts subclass it and add in-memory
repositories that call `track()`."""

from datetime import UTC, datetime
from types import TracebackType
from typing import Self

from riso.shared import (
    Clock,
    DomainEvent,
    EventDispatcher,
    FixedClock,
    HasEvents,
    IdGenerator,
    UuidV7Generator,
)


class InMemoryUnitOfWork:
    def __init__(
        self,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
        dispatcher: EventDispatcher | None = None,
    ) -> None:
        self.clock: Clock = clock or FixedClock(datetime(2026, 6, 11, 8, 0, tzinfo=UTC))
        self.ids: IdGenerator = ids or UuidV7Generator(self.clock)
        self.dispatcher = dispatcher or EventDispatcher()
        self.commits = 0
        self.rollbacks = 0
        self.dispatched: list[DomainEvent] = []
        self._tracked: list[HasEvents] = []

    def __enter__(self) -> Self:
        self._tracked = []
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._tracked or exc_type is not None:
            self.rollback()

    def track(self, aggregate: HasEvents) -> None:
        if not any(tracked is aggregate for tracked in self._tracked):
            self._tracked.append(aggregate)

    def commit(self) -> None:
        events = [e for a in self._tracked for e in a.events]
        self._forget()
        self.commits += 1
        self.dispatched += events
        self.dispatcher.dispatch(events)

    def rollback(self) -> None:
        self._forget()
        self.rollbacks += 1

    def _forget(self) -> None:
        for aggregate in self._tracked:
            aggregate.events.clear()
        self._tracked.clear()
