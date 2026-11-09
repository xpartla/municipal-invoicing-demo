"""The repository protocols of the exchange context. An import run belongs to a customer or,
for a global list, to the platform (None); every method takes that owner (guide §6.4)."""

from typing import Protocol

from riso.exchange.domain.run import ImportRun


class ImportRunRepository(Protocol):
    def add(self, run: ImportRun) -> None: ...

    def save(self, run: ImportRun) -> None: ...

    def get(self, customer_id: str | None, run_id: str) -> ImportRun:
        """Raises `NotFound` when the owner has no such run."""
        ...

    def list(self, customer_id: str | None, *, offset: int, limit: int) -> list[ImportRun]:
        """The owner's runs, the newest first."""
        ...

    def count(self, customer_id: str | None) -> int: ...
