"""The job repository protocol."""

from datetime import datetime
from typing import Protocol

from riso.jobs.domain.job import Job


class JobRepository(Protocol):
    def add(self, job: Job) -> None: ...

    def get(self, job_id: str) -> Job:
        """Raises `NotFound` when there is no such job."""
        ...

    def next_claimable(self, at: datetime) -> Job | None:
        """The job to run next: queued and due, or running with an expired lease; the
        earliest `run_after` first. Called inside a transaction that holds the write lock."""
        ...

    def save(self, job: Job) -> None: ...
