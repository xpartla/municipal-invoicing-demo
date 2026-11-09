"""The jobs API: a customer's job, for the pages that follow one
(`/api/customers/{customer_id}/jobs/{job_id}`)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from riso.api.deps import Caller, ServicesDep, check_csrf, customer_context
from riso.identity import Permission
from riso.jobs.api.models import JobOut
from riso.jobs.application import get_customer_job

router = APIRouter(prefix="/api", dependencies=[Depends(check_csrf)], tags=["jobs"])


@router.get("/customers/{customer_id}/jobs/{job_id}", name="jobs.get_customer")
def customer_job(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
    job_id: str,
) -> JobOut:
    """The state of one of the customer's jobs (a copy, an import's dry run or apply)."""
    return JobOut.of(
        get_customer_job(caller.ctx, services.jobs_uow(immediate=False), customer_id, job_id)
    )
