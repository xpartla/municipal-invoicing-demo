"""The jobs API: a customer's job, for the pages that follow one
(`/api/customers/{customer_id}/jobs/{job_id}`), and the admin's Úlohy (`/api/admin/jobs`):
the list, retry, cancel, and the file of a customer data export."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Query, Response

from riso.api.deps import Caller, ServicesDep, check_csrf, customer_context, platform_context
from riso.identity import Permission
from riso.jobs.api.models import AdminJobOut, AdminJobPageOut, JobOut
from riso.jobs.application import (
    JobFilter,
    cancel_job,
    data_export_file,
    get_customer_job,
    list_jobs,
    retry_job,
)
from riso.jobs.domain import JobStatus

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


JobsAdmin = Annotated[Caller, Depends(platform_context(Permission.JOBS_MANAGE))]
JobId = Annotated[str, Path(max_length=36)]


@router.get("/admin/jobs", name="jobs.list")
def admin_jobs(
    caller: JobsAdmin,
    services: ServicesDep,
    status: JobStatus | None = None,
    kind: Annotated[str | None, Query(max_length=40)] = None,
    customer_id: Annotated[str | None, Query(max_length=36)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AdminJobPageOut:
    """Every job, the newest first, with its state, attempts and last error (Úlohy)."""
    found = list_jobs(
        caller.ctx,
        services.uow(immediate=False),
        JobFilter(status, kind, customer_id),
        page=page,
        size=size,
    )
    return AdminJobPageOut(
        items=[AdminJobOut.of(j) for j in found.items], total=found.total, kinds=found.kinds
    )


@router.post("/admin/jobs/{job_id}/retry", name="jobs.retry")
def admin_retry_job(caller: JobsAdmin, services: ServicesDep, job_id: JobId) -> AdminJobOut:
    """Runs a failed job again with a fresh set of attempts (audited); 409 for another state."""
    return AdminJobOut.of(retry_job(caller.ctx, services.uow(), job_id))


@router.post("/admin/jobs/{job_id}/cancel", name="jobs.cancel")
def admin_cancel_job(caller: JobsAdmin, services: ServicesDep, job_id: JobId) -> AdminJobOut:
    """Cancels a queued job (audited); 409 for another state."""
    return AdminJobOut.of(cancel_job(caller.ctx, services.uow(), job_id))


@router.get("/admin/jobs/{job_id}/file", name="jobs.file")
def admin_job_file(
    caller: Annotated[Caller, Depends(platform_context(Permission.CUSTOMER_DATA_EXPORT))],
    services: ServicesDep,
    job_id: JobId,
) -> Response:
    """The ZIP of a finished customer data export; 404 for another job."""
    found = data_export_file(caller.ctx, services.uow(immediate=False), job_id)
    with services.storage.open(found.key) as source:
        data = source.read()
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(found.name)}"},
    )
