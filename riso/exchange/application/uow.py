"""The unit of work the exchange use cases need: the import runs and templates, the code lists
they make versions of, the job queue, the audit log and the supplier memory, on one
transaction."""

from typing import Protocol

from riso.codelists import CodelistsUnitOfWork
from riso.exchange.application.ports import PrecedentSink
from riso.exchange.domain.repository import ImportRunRepository, TemplateRepository
from riso.jobs import JobQueue


class ExchangeUnitOfWork(CodelistsUnitOfWork, Protocol):
    @property
    def imports(self) -> ImportRunRepository: ...

    @property
    def templates(self) -> TemplateRepository: ...

    @property
    def queue(self) -> JobQueue: ...

    @property
    def precedents(self) -> PrecedentSink:
        """The supplier memory and number series, in this unit of work."""
        ...
