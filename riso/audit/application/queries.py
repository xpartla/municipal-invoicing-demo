"""Reading the audit log (the admin's viewer, plan §10.9)."""

from typing import Protocol

from riso.audit.domain import AuditEvent, AuditFilter
from riso.identity import Permission
from riso.shared.context import RequestContext
from riso.shared.uow import UnitOfWork


class AuditLog(Protocol):
    def page(
        self, where: AuditFilter, *, page: int = 1, size: int = 50
    ) -> tuple[list[AuditEvent], int]:
        """Newest first, and the total."""
        ...


class AuditUnitOfWork(UnitOfWork, Protocol):
    @property
    def audit_log(self) -> AuditLog: ...


def list_events(
    ctx: RequestContext,
    uow: AuditUnitOfWork,
    where: AuditFilter,
    *,
    page: int = 1,
    size: int = 50,
) -> tuple[list[AuditEvent], int]:
    ctx.require(Permission.AUDIT_READ)
    with uow:
        return uow.audit_log.page(where, page=page, size=size)
