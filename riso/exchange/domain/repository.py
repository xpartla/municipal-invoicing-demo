"""The repository protocols of the exchange context. An import run belongs to a customer or,
for a global list, to the platform (None); every method takes that owner (guide §6.4)."""

from typing import Protocol

from riso.exchange.domain.export import ExportRun
from riso.exchange.domain.run import ImportRun
from riso.exchange.domain.templates import MappingTemplate, TemplateScope


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


class TemplateRepository(Protocol):
    """Stored templates (built-in ones live in the code). `owner_id` is the customer's or the
    provider's ID, None for a global template."""

    def add(self, template: MappingTemplate) -> None: ...

    def save(self, template: MappingTemplate) -> None: ...

    def delete(self, template: MappingTemplate) -> None: ...

    def get(self, scope: TemplateScope, owner_id: str | None, template_id: str) -> MappingTemplate:
        """Raises `NotFound` unless the template has that scope and owner."""
        ...

    def owned(self, scope: TemplateScope, owner_id: str | None) -> list[MappingTemplate]:
        """The scope's and owner's templates, by name."""
        ...


class ExportRunRepository(Protocol):
    def add(self, run: ExportRun) -> None: ...

    def save(self, run: ExportRun) -> None: ...

    def get(self, customer_id: str, run_id: str) -> ExportRun:
        """Raises `NotFound` when the customer has no such export."""
        ...

    def list(self, customer_id: str, *, offset: int, limit: int) -> list[ExportRun]:
        """The customer's exports, the newest first."""
        ...

    def count(self, customer_id: str) -> int: ...
