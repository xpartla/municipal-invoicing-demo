"""Enqueueing jobs, and the views of a job.

Other contexts enqueue through the `JobQueue` port, which their unit of work provides on
its own session, so a job is queued exactly when the change that needs it commits.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from riso.jobs.application.registry import JobRegistry
from riso.jobs.domain import Job, JobRepository, JobStatus
from riso.shared.clock import Clock
from riso.shared.ids import IdGenerator
from riso.shared.uow import UnitOfWork


class JobQueue(Protocol):
    def enqueue(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        customer_id: str | None = None,
        created_by: str | None = None,
        run_after: datetime | None = None,
    ) -> str:
        """Queues a job and returns its ID. Raises `NotFound` for an unknown kind and
        `ValidationFailed` for a payload its model refuses."""
        ...


class JobsUnitOfWork(UnitOfWork, Protocol):
    @property
    def jobs(self) -> JobRepository: ...

    @property
    def queue(self) -> JobQueue: ...


class RepositoryJobQueue:
    """A `JobQueue` writing through a job repository; a unit of work builds one on its
    session."""

    def __init__(
        self, jobs: JobRepository, registry: JobRegistry, clock: Clock, ids: IdGenerator
    ) -> None:
        self._jobs = jobs
        self._registry = registry
        self._clock = clock
        self._ids = ids

    def enqueue(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        customer_id: str | None = None,
        created_by: str | None = None,
        run_after: datetime | None = None,
    ) -> str:
        stored = self._registry.validate(kind, payload)
        job = Job.new(
            self._ids.new(),
            kind,
            stored,
            self._clock.now(),
            created_by=created_by,
            customer_id=customer_id,
            run_after=run_after,
            max_attempts=self._registry.kind(kind).max_attempts,
        )
        self._jobs.add(job)
        return job.id


@dataclass(frozen=True, slots=True)
class JobView:
    id: str
    kind: str
    status: JobStatus
    attempts: int
    max_attempts: int
    created_at: datetime
    run_after: datetime
    started_at: datetime | None
    finished_at: datetime | None
    customer_id: str | None
    last_error: str | None
    result: dict[str, Any] | None

    @classmethod
    def of(cls, job: Job) -> "JobView":
        return cls(
            id=job.id,
            kind=job.kind,
            status=job.status,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            created_at=job.created_at,
            run_after=job.run_after,
            started_at=job.started_at,
            finished_at=job.finished_at,
            customer_id=job.customer_id,
            last_error=job.last_error,
            result=job.result,
        )
