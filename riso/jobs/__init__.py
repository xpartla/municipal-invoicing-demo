"""The jobs context: background work: the job queue, claiming and retries, the registry of job
kinds, and the worker. Main aggregates: Job. This module is the context's public surface: other
contexts import only what it exports (its application API), never its domain, infrastructure or
api modules. See plan §4.2 and guide §6.1."""

from riso.jobs.application import (
    JobContext,
    JobKind,
    JobQueue,
    JobRegistry,
    JobsUnitOfWork,
    JobView,
    Worker,
    get_customer_job,
    register_builtin,
)
from riso.jobs.domain import JobStatus, RetryPolicy

__all__ = [
    "JobContext",
    "JobKind",
    "JobQueue",
    "JobRegistry",
    "JobStatus",
    "JobView",
    "JobsUnitOfWork",
    "RetryPolicy",
    "Worker",
    "get_customer_job",
    "register_builtin",
]
