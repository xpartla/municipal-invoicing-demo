"""The unit of work the codelists use cases need."""

from typing import Protocol

from riso.codelists.domain import CodeListRepository
from riso.shared.ports import AuditRecorder
from riso.shared.uow import UnitOfWork


class CodelistsUnitOfWork(UnitOfWork, Protocol):
    @property
    def codelists(self) -> CodeListRepository: ...

    @property
    def audit(self) -> AuditRecorder: ...
