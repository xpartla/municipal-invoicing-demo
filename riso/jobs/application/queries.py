"""Reading a job: a customer's own job, for a page that follows it (a customer copy, an
import's dry run). The admin's job list (Úlohy) comes with the admin screens."""

from riso.identity import Permission
from riso.jobs.application.queue import JobsUnitOfWork, JobView
from riso.shared.context import RequestContext
from riso.shared.errors import NotFound


def get_customer_job(
    ctx: RequestContext, uow: JobsUnitOfWork, customer_id: str, job_id: str
) -> JobView:
    """The job, when it belongs to the customer; `NotFound` otherwise."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        job = uow.jobs.get(job_id)
    if job.customer_id != customer_id:
        raise NotFound(f"no job {job_id}")
    return JobView.of(job)
