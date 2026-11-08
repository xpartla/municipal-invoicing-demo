"""The codelists API: a customer's code lists, conventions and their health
(`/api/customers/{customer_id}/…`), and the global lists (`/api/admin/…`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from riso.api.deps import Caller, ServicesDep, check_csrf, customer_context
from riso.codelists.api.models import HealthReportOut
from riso.codelists.application import knowledge_health
from riso.identity import Permission
from riso.shared.clock import local_date

router = APIRouter(prefix="/api", dependencies=[Depends(check_csrf)], tags=["codelists"])

Year = Annotated[int | None, Query(ge=2000, le=2100, description="Default: this year")]


@router.get("/customers/{customer_id}/health", name="codelists.health")
def health(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
    year: Year = None,
) -> HealthReportOut:
    """The knowledge health report (plan §6.5): missing lists, conventions naming missing
    accounts, budget EKs without a bridge rule, precedents outside the active lists."""
    chosen = year or local_date(services.clock.now()).year
    memory = services.supplier_state().memory(customer_id)
    findings = knowledge_health(
        caller.ctx, services.uow(immediate=False), customer_id, chosen, memory
    )
    return HealthReportOut.of(chosen, findings)
