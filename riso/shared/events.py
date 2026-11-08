"""Domain events. Aggregates append them to their `events` list; the unit of work collects
them and dispatches them in process after the transaction commits (plan §4.7).

Handlers run after the commit, so a handler's failure cannot undo the write that raised
the event. A failing handler is logged and the others still run. Work that must be atomic
with the write belongs in the use case itself, not in a handler.
"""

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Base of all events. Subclasses are frozen dataclasses carrying IDs and instants."""


E = TypeVar("E", bound=DomainEvent)
Handler = Callable[[Any], None]


class HasEvents(Protocol):
    """An aggregate that records events."""

    events: list[DomainEvent]


class EventDispatcher:
    """Calls the handlers subscribed to an event's type, or to any of its base classes,
    in subscription order."""

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        self._handlers[event_type].append(handler)

    def dispatch(self, events: Iterable[DomainEvent]) -> None:
        for event in events:
            for event_type in type(event).__mro__:
                for handler in self._handlers.get(event_type, ()):
                    try:
                        handler(event)
                    except Exception:
                        log.exception(
                            "event handler %s failed for %s",
                            getattr(handler, "__qualname__", repr(handler)),
                            type(event).__name__,
                        )
