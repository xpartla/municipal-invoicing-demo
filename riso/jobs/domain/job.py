"""A background job and its lifecycle (plan §4.6).

    queued ──claim──> running ──succeed──> succeeded
      │                 │  └──fail, attempts left──> queued (run_after = now + backoff)
      │                 └──fail, no attempts left, or a permanent failure──> failed
      └──cancel──> cancelled                   failed ──retry (admin)──> queued

A running job whose lease ran out (its worker stopped) can be claimed again; that counts as
a failed attempt. Error texts are kept per attempt; they carry exception types and IDs,
never document content.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from riso.shared.errors import InvalidState

MAX_ERROR_LENGTH = 500


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TRANSITIONS: frozenset[tuple[JobStatus, JobStatus]] = frozenset(
    {
        (JobStatus.QUEUED, JobStatus.RUNNING),
        (JobStatus.RUNNING, JobStatus.RUNNING),  # reclaimed after the lease ran out
        (JobStatus.RUNNING, JobStatus.SUCCEEDED),
        (JobStatus.RUNNING, JobStatus.QUEUED),  # failed with attempts left
        (JobStatus.RUNNING, JobStatus.FAILED),
        (JobStatus.QUEUED, JobStatus.CANCELLED),
        (JobStatus.FAILED, JobStatus.QUEUED),  # retried by an admin
    }
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """The delay before attempt n + 1 after attempt n failed: base × factor^(n − 1)."""

    base_delay: timedelta = timedelta(seconds=5)
    factor: int = 2

    def delay(self, attempt: int) -> timedelta:
        return self.base_delay * int(self.factor ** max(attempt - 1, 0))


@dataclass(frozen=True, slots=True)
class JobError:
    attempt: int
    at: datetime
    message: str


@dataclass(slots=True)
class Job:
    id: str
    kind: str
    payload: dict[str, Any]
    created_at: datetime
    run_after: datetime
    status: JobStatus = JobStatus.QUEUED
    attempts: int = 0
    max_attempts: int = 3
    created_by: str | None = None
    customer_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    locked_by: str | None = None
    locked_until: datetime | None = None
    errors: list[JobError] = field(default_factory=list)
    result: dict[str, Any] | None = None

    @classmethod
    def new(
        cls,
        job_id: str,
        kind: str,
        payload: dict[str, Any],
        at: datetime,
        *,
        created_by: str | None = None,
        customer_id: str | None = None,
        run_after: datetime | None = None,
        max_attempts: int = 3,
    ) -> "Job":
        if max_attempts < 1:
            raise ValueError("a job needs at least one attempt")
        return cls(
            id=job_id,
            kind=kind,
            payload=payload,
            created_at=at,
            run_after=run_after or at,
            created_by=created_by,
            customer_id=customer_id,
            max_attempts=max_attempts,
        )

    @property
    def last_error(self) -> str | None:
        return self.errors[-1].message if self.errors else None

    def is_claimable(self, at: datetime) -> bool:
        if self.status is JobStatus.QUEUED:
            return self.run_after <= at
        return self.status is JobStatus.RUNNING and self._lease_expired(at)

    def claim(self, at: datetime, worker_id: str, lease: timedelta) -> bool:
        """Starts an attempt. Returns False when the job cannot run any more: it was
        reclaimed after its lease ran out and that was its last attempt."""
        if not self.is_claimable(at):
            raise InvalidState(f"job {self.id} is {self.status} and cannot be claimed")
        if self.status is JobStatus.RUNNING:
            self._record_error(at, "the worker stopped before finishing (lease expired)")
            if self.attempts >= self.max_attempts:
                self._finish(JobStatus.FAILED, at)
                return False
        self._move(JobStatus.RUNNING)
        self.attempts += 1
        self.started_at = at
        self.locked_by = worker_id
        self.locked_until = at + lease
        return True

    def succeed(self, at: datetime, result: dict[str, Any] | None = None) -> None:
        self._require_running()
        self.result = result
        self._finish(JobStatus.SUCCEEDED, at)

    def fail(
        self, at: datetime, error: str, retry: RetryPolicy, *, permanent: bool = False
    ) -> None:
        """Records a failed attempt. With attempts left, and unless the failure is permanent
        (an unknown kind, an invalid payload), the job is queued again after the backoff."""
        self._require_running()
        self._record_error(at, error)
        if permanent or self.attempts >= self.max_attempts:
            self._finish(JobStatus.FAILED, at)
            return
        self._move(JobStatus.QUEUED)
        self.run_after = at + retry.delay(self.attempts)
        self.locked_by = None
        self.locked_until = None

    def cancel(self, at: datetime) -> None:
        self._move(JobStatus.CANCELLED)
        self.finished_at = at

    def retry(self, at: datetime) -> None:
        """An admin runs a failed job again, with a fresh set of attempts."""
        if self.status is not JobStatus.FAILED:
            raise InvalidState(f"job {self.id} is {self.status}; only a failed job is retried")
        self._move(JobStatus.QUEUED)
        self.attempts = 0
        self.run_after = at
        self.finished_at = None

    def _lease_expired(self, at: datetime) -> bool:
        return self.locked_until is not None and self.locked_until <= at

    def _require_running(self) -> None:
        if self.status is not JobStatus.RUNNING:
            raise InvalidState(f"job {self.id} is {self.status}, not running")

    def _record_error(self, at: datetime, message: str) -> None:
        self.errors.append(JobError(self.attempts, at, message[:MAX_ERROR_LENGTH]))

    def _finish(self, status: JobStatus, at: datetime) -> None:
        self._move(status)
        self.finished_at = at
        self.locked_by = None
        self.locked_until = None

    def _move(self, to: JobStatus) -> None:
        if (self.status, to) not in TRANSITIONS:
            raise InvalidState(f"job {self.id} cannot go from {self.status} to {to}")
        self.status = to
