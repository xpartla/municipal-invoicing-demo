"""The unit of work: one transaction per command (guide §6.3).

    with uow:
        invoice = uow.invoices.get(customer_id, invoice_id)  # repositories track aggregates
        invoice.book(coding, uow.clock.now(), ctx.actor_id)
        uow.commit()                                          # events dispatched after

Leaving the block without `commit()`, or with an exception, rolls back and discards the
tracked aggregates' events. Repositories call `track()` on every aggregate they hand out or
add, so `commit()` can collect the events those aggregates recorded.
"""

from types import TracebackType
from typing import Protocol, Self

from riso.shared.clock import Clock
from riso.shared.events import HasEvents
from riso.shared.ids import IdGenerator


class UnitOfWork(Protocol):
    # Read-only, so an implementation may hold a more specific type.
    @property
    def clock(self) -> Clock: ...

    @property
    def ids(self) -> IdGenerator: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None:
        """Commits the transaction, then dispatches the tracked aggregates' events."""
        ...

    def rollback(self) -> None:
        """Rolls back and discards the tracked aggregates' events."""
        ...

    def track(self, aggregate: HasEvents) -> None:
        """Registers an aggregate whose events `commit()` dispatches."""
        ...
