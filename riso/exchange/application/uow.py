"""The unit of work the exchange use cases need: the import runs and templates, the code lists
they make versions of, the job queue and the audit log, on one transaction."""

from typing import Protocol

from riso.codelists import CodelistsUnitOfWork
from riso.exchange.domain.repository import ImportRunRepository, TemplateRepository
from riso.jobs import JobQueue


class ExchangeUnitOfWork(CodelistsUnitOfWork, Protocol):
    @property
    def imports(self) -> ImportRunRepository: ...

    @property
    def templates(self) -> TemplateRepository: ...

    @property
    def queue(self) -> JobQueue: ...
