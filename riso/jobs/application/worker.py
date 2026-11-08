"""The worker: claims due jobs one at a time and runs them.

Claiming is a short transaction that takes the write lock first (`BEGIN IMMEDIATE`), so two
workers never claim the same job. The handler runs outside any transaction, and the outcome
is saved in a second short one. Tests call `run_pending()`; the app runs the worker in a
thread (see `riso.jobs.infrastructure.thread`), and `riso worker` in its own process.
"""

import logging
from collections.abc import Callable
from datetime import timedelta

from pydantic import ValidationError

from riso.jobs.application.queue import JobsUnitOfWork
from riso.jobs.application.registry import JobContext, JobRegistry
from riso.jobs.domain import Job, JobStatus, RetryPolicy
from riso.shared.context import RequestContext
from riso.shared.errors import NotFound

log = logging.getLogger(__name__)

UnitOfWorkFactory = Callable[[bool], JobsUnitOfWork]
"""Makes a jobs unit of work; the argument asks for BEGIN IMMEDIATE (on SQLite)."""

ContextFactory = Callable[[Job], RequestContext]

DEFAULT_LEASE = timedelta(minutes=10)


def anonymous_job_context(job: Job) -> RequestContext:
    """The context of a job until P2-M1 supplies one with the starter's permissions."""
    return RequestContext(request_id=f"job:{job.id}", actor_id=job.created_by)


class Worker:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        registry: JobRegistry,
        *,
        worker_id: str,
        lease: timedelta = DEFAULT_LEASE,
        retry: RetryPolicy | None = None,
        context_factory: ContextFactory = anonymous_job_context,
    ) -> None:
        self._uow = uow_factory
        self._registry = registry
        self.worker_id = worker_id
        self._lease = lease
        self._retry = retry or RetryPolicy()
        self._context = context_factory

    def run_pending(self, limit: int = 1000) -> int:
        """Runs due jobs until none is left, or `limit` were run. Returns how many ran."""
        ran = 0
        while ran < limit and self.run_once():
            ran += 1
        return ran

    def run_once(self) -> bool:
        """Claims and runs one due job. Returns False when none was due."""
        job = self._claim()
        if job is None:
            return False
        if job.status is not JobStatus.RUNNING:
            return True  # its lease ran out on the last attempt: claiming failed it
        self._run(job)
        return True

    def _claim(self) -> Job | None:
        with self._uow(True) as uow:
            now = uow.clock.now()
            job = uow.jobs.next_claimable(now)
            if job is None:
                return None
            job.claim(now, self.worker_id, self._lease)
            uow.jobs.save(job)
            uow.commit()
            return job

    def _run(self, job: Job) -> None:
        permanent = False
        try:
            kind = self._registry.kind(job.kind)
            payload = kind.payload.model_validate(job.payload)
        except (NotFound, ValidationError) as exc:
            permanent, error = True, _describe(exc)
        else:
            context = JobContext(
                job_id=job.id,
                kind=job.kind,
                attempt=job.attempts,
                customer_id=job.customer_id,
                created_by=job.created_by,
                request=self._context(job),
            )
            try:
                result = kind.handler(payload, context)
            except Exception as exc:
                log.warning("job %s (%s) attempt %d failed", job.id, job.kind, job.attempts)
                error = _describe(exc)
            else:
                self._finish(job.id, result=result)
                return
        self._finish(job.id, error=error, permanent=permanent)

    def _finish(
        self,
        job_id: str,
        *,
        result: dict[str, object] | None = None,
        error: str | None = None,
        permanent: bool = False,
    ) -> None:
        with self._uow(True) as uow:  # reads, then writes: take the write lock first
            job = uow.jobs.get(job_id)
            now = uow.clock.now()
            if error is None:
                job.succeed(now, result)
            else:
                job.fail(now, error, self._retry, permanent=permanent)
            uow.jobs.save(job)
            uow.commit()


def _describe(exc: BaseException) -> str:
    """The exception type and message. Our handlers put IDs in messages, never content."""
    return f"{type(exc).__name__}: {exc}"
