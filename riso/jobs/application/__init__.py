"""Use cases (commands and queries), views (DTOs) and ports of the jobs context. A use case checks
its permission first, runs in one unit of work, and returns views, never entities or ORM
objects."""

from riso.jobs.application.builtin import NoopPayload, register_builtin
from riso.jobs.application.queue import JobQueue, JobsUnitOfWork, JobView, RepositoryJobQueue
from riso.jobs.application.registry import JobContext, JobKind, JobRegistry
from riso.jobs.application.worker import Worker, anonymous_job_context

__all__ = [
    "JobContext",
    "JobKind",
    "JobQueue",
    "JobRegistry",
    "JobView",
    "JobsUnitOfWork",
    "NoopPayload",
    "RepositoryJobQueue",
    "Worker",
    "anonymous_job_context",
    "register_builtin",
]
