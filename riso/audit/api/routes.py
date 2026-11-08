"""The audit API: the admin's search over the log (`/api/admin/audit`). The viewer screen
comes in P2-M7."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from riso.api.deps import Caller, ServicesDep, check_csrf, platform_context
from riso.audit.application import list_events
from riso.audit.domain import AuditEvent, AuditFilter
from riso.identity import Permission

router = APIRouter(prefix="/api/admin", dependencies=[Depends(check_csrf)], tags=["audit"])


class AuditEventOut(BaseModel):
    id: str
    at: datetime
    action: str
    actor_id: str | None
    real_actor_id: str | None
    customer_id: str | None
    target_type: str | None
    target_id: str | None
    details: dict[str, Any]
    request_id: str | None
    ip: str | None

    @classmethod
    def of(cls, event: AuditEvent) -> "AuditEventOut":
        return cls(
            id=event.id,
            at=event.at,
            action=event.action,
            actor_id=event.actor_id,
            real_actor_id=event.real_actor_id,
            customer_id=event.customer_id,
            target_type=event.target_type,
            target_id=event.target_id,
            details=event.details,
            request_id=event.request_id,
            ip=event.ip,
        )


class AuditPageOut(BaseModel):
    items: list[AuditEventOut]
    total: int


@router.get("/audit", name="audit.list")
def audit_list(
    caller: Annotated[Caller, Depends(platform_context(Permission.AUDIT_READ))],
    services: ServicesDep,
    actor_id: Annotated[str | None, Query(max_length=36)] = None,
    customer_id: Annotated[str | None, Query(max_length=36)] = None,
    action: Annotated[str | None, Query(max_length=80)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditPageOut:
    """Newest first. `actor_id` matches the actor or the real actor; `action` is a whole
    action or a prefix ending in a dot."""
    events, total = list_events(
        caller.ctx,
        services.uow(immediate=False),
        AuditFilter(actor_id, customer_id, action, since, until),
        page=page,
        size=size,
    )
    return AuditPageOut(items=[AuditEventOut.of(e) for e in events], total=total)
