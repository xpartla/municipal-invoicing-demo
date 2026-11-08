"""Writing and reading the audit log on SQLAlchemy."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from riso.audit.domain import AuditEvent, AuditFilter
from riso.audit.infrastructure.orm import AuditEventRow
from riso.shared.clock import Clock
from riso.shared.context import RequestContext
from riso.shared.ids import IdGenerator


class SqlAuditRecorder:
    """The `AuditRecorder` port: adds a row to the caller's session, so the entry commits
    with the change it records, or not at all."""

    def __init__(self, session: Session, clock: Clock, ids: IdGenerator) -> None:
        self._session = session
        self._clock = clock
        self._ids = ids

    def record(
        self,
        ctx: RequestContext,
        action: str,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
        customer_id: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self._session.add(
            AuditEventRow(
                id=self._ids.new(),
                at=self._clock.now(),
                action=action,
                actor_id=ctx.actor_id,
                real_actor_id=ctx.real_actor_id,
                customer_id=customer_id or ctx.customer_id,
                target_type=target_type,
                target_id=target_id,
                details=dict(details or {}),
                request_id=ctx.request_id,
                ip=ctx.ip,
            )
        )


class SqlAuditLog:
    """Reading the log, for the admin's viewer and the tests."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def page(
        self, where: AuditFilter, *, page: int = 1, size: int = 50
    ) -> tuple[list[AuditEvent], int]:
        query = select(AuditEventRow)
        if where.actor_id:
            query = query.where(
                or_(
                    AuditEventRow.actor_id == where.actor_id,
                    AuditEventRow.real_actor_id == where.actor_id,
                )
            )
        if where.customer_id:
            query = query.where(AuditEventRow.customer_id == where.customer_id)
        if where.action:
            if where.action.endswith("."):
                query = query.where(AuditEventRow.action.startswith(where.action, autoescape=True))
            else:
                query = query.where(AuditEventRow.action == where.action)
        if where.since:
            query = query.where(AuditEventRow.at >= where.since)
        if where.until:
            query = query.where(AuditEventRow.at < where.until)
        total = self._session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self._session.scalars(
            query.order_by(AuditEventRow.at.desc(), AuditEventRow.id.desc())
            .limit(size)
            .offset((page - 1) * size)
        ).all()
        return [_event(row) for row in rows], total


def _event(row: AuditEventRow) -> AuditEvent:
    details: dict[str, Any] = dict(row.details)
    return AuditEvent(
        id=row.id,
        at=row.at,
        action=row.action,
        actor_id=row.actor_id,
        real_actor_id=row.real_actor_id,
        customer_id=row.customer_id,
        target_type=row.target_type,
        target_id=row.target_id,
        details=details,
        request_id=row.request_id,
        ip=row.ip,
    )
