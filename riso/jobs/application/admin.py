"""Úlohy, the admin's jobs (plan §10.9, decision 67): the list with filters, retrying a failed
job and cancelling a queued one (the transitions the job's state machine allows), each
audited; and the file a finished customer data export left."""

from dataclasses import dataclass
from typing import Protocol

from riso.identity import Permission
from riso.jobs.application.queue import JobView
from riso.jobs.domain import Job, JobRepository, JobStatus
from riso.shared.context import RequestContext
from riso.shared.errors import NotFound
from riso.shared.ports import AuditRecorder
from riso.shared.uow import UnitOfWork

DATA_EXPORT_KIND = "data_export"


@dataclass(frozen=True, slots=True)
class JobFilter:
    status: JobStatus | None = None
    kind: str | None = None
    customer_id: str | None = None


class JobListing(Protocol):
    def page(self, where: JobFilter, *, offset: int, limit: int) -> tuple[list[Job], int]:
        """The newest first, and the total."""
        ...

    def kinds(self) -> list[str]:
        """Every kind a stored job has, by name."""
        ...


class JobsAdminUnitOfWork(UnitOfWork, Protocol):
    @property
    def jobs(self) -> JobRepository: ...

    @property
    def job_listing(self) -> JobListing: ...

    @property
    def audit(self) -> AuditRecorder: ...


@dataclass(frozen=True, slots=True)
class JobPage:
    items: list[JobView]
    total: int
    kinds: list[str]


def list_jobs(
    ctx: RequestContext, uow: JobsAdminUnitOfWork, where: JobFilter, *, page: int, size: int
) -> JobPage:
    ctx.require(Permission.JOBS_MANAGE)
    with uow:
        jobs, total = uow.job_listing.page(where, offset=(page - 1) * size, limit=size)
        return JobPage([JobView.of(j) for j in jobs], total, uow.job_listing.kinds())


def _change(ctx: RequestContext, uow: JobsAdminUnitOfWork, job_id: str, action: str) -> JobView:
    ctx.require(Permission.JOBS_MANAGE)
    with uow:
        job = uow.jobs.get(job_id)
        before = job.status
        at = uow.clock.now()
        if action == "job.retried":
            job.retry(at)
        else:
            job.cancel(at)
        uow.jobs.save(job)
        uow.audit.record(
            ctx,
            action,
            target_type="job",
            target_id=job.id,
            customer_id=job.customer_id,
            details={"kind": job.kind, "from": before.value},
        )
        uow.commit()
    return JobView.of(job)


def retry_job(ctx: RequestContext, uow: JobsAdminUnitOfWork, job_id: str) -> JobView:
    """A failed job runs again with a fresh set of attempts; another state is a 409."""
    return _change(ctx, uow, job_id, "job.retried")


def cancel_job(ctx: RequestContext, uow: JobsAdminUnitOfWork, job_id: str) -> JobView:
    """A queued job will not run; another state is a 409."""
    return _change(ctx, uow, job_id, "job.cancelled")


@dataclass(frozen=True, slots=True)
class ExportedFile:
    key: str
    name: str


def data_export_file(ctx: RequestContext, uow: JobsAdminUnitOfWork, job_id: str) -> ExportedFile:
    """Where the ZIP a finished customer data export stored is, and its name; `NotFound` for
    another job (the caller reads it from the store)."""
    ctx.require(Permission.CUSTOMER_DATA_EXPORT)
    with uow:
        job = uow.jobs.get(job_id)
    result = job.result or {}
    key, name = result.get("file_key"), result.get("name")
    if (
        job.kind != DATA_EXPORT_KIND
        or job.status is not JobStatus.SUCCEEDED
        or not isinstance(key, str)
        or not isinstance(name, str)
    ):
        raise NotFound(f"job {job_id} has no data export")
    return ExportedFile(key, name)
