"""The job repository on SQLAlchemy, mapping rows to `Job` and back explicitly."""

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from riso.jobs.domain import Job, JobError, JobStatus
from riso.jobs.infrastructure.orm import JobRow
from riso.shared.errors import NotFound


class SqlJobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, job: Job) -> None:
        row = JobRow(id=job.id)
        _write(job, row)
        self._session.add(row)

    def get(self, job_id: str) -> Job:
        row = self._session.get(JobRow, job_id)
        if row is None:
            raise NotFound(f"no job {job_id}")
        return read_job(row)

    def next_claimable(self, at: datetime) -> Job | None:
        # SQLite: the caller's BEGIN IMMEDIATE holds the write lock, so no other worker can
        # claim between this read and the save. PostgreSQL would add FOR UPDATE SKIP LOCKED.
        due = or_(
            and_(JobRow.status == JobStatus.QUEUED.value, JobRow.run_after <= at),
            and_(JobRow.status == JobStatus.RUNNING.value, JobRow.locked_until <= at),
        )
        row = self._session.scalars(
            select(JobRow).where(due).order_by(JobRow.run_after, JobRow.id).limit(1)
        ).first()
        return None if row is None else read_job(row)

    def save(self, job: Job) -> None:
        row = self._session.get(JobRow, job.id)
        if row is None:
            raise NotFound(f"no job {job.id}")
        _write(job, row)


def _write(job: Job, row: JobRow) -> None:
    row.kind = job.kind
    row.payload = job.payload
    row.status = job.status.value
    row.attempts = job.attempts
    row.max_attempts = job.max_attempts
    row.created_at = job.created_at
    row.run_after = job.run_after
    row.created_by = job.created_by
    row.customer_id = job.customer_id
    row.started_at = job.started_at
    row.finished_at = job.finished_at
    row.locked_by = job.locked_by
    row.locked_until = job.locked_until
    row.last_error = job.last_error
    row.errors = [
        {"attempt": e.attempt, "at": e.at.isoformat(), "message": e.message} for e in job.errors
    ]
    row.result = job.result


def read_job(row: JobRow) -> Job:
    return Job(
        id=row.id,
        kind=row.kind,
        payload=dict(row.payload),
        created_at=row.created_at,
        run_after=row.run_after,
        status=JobStatus(row.status),
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        created_by=row.created_by,
        customer_id=row.customer_id,
        started_at=row.started_at,
        finished_at=row.finished_at,
        locked_by=row.locked_by,
        locked_until=row.locked_until,
        errors=[
            JobError(e["attempt"], datetime.fromisoformat(e["at"]), e["message"])
            for e in row.errors
        ],
        result=row.result,
    )
