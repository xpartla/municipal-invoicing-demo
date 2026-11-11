"""Request and response models of the jobs API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from riso.jobs.application import JobView
from riso.jobs.domain import JobStatus


class JobOut(BaseModel):
    id: str
    kind: str
    status: JobStatus
    attempts: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    last_error: str | None
    result: dict[str, Any] | None

    @classmethod
    def of(cls, view: JobView) -> "JobOut":
        return cls(
            id=view.id,
            kind=view.kind,
            status=view.status,
            attempts=view.attempts,
            max_attempts=view.max_attempts,
            created_at=view.created_at,
            started_at=view.started_at,
            finished_at=view.finished_at,
            last_error=view.last_error,
            result=view.result,
        )


class AdminJobOut(BaseModel):
    """A job as Úlohy shows it."""

    id: str
    kind: str
    status: JobStatus
    attempts: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    customer_id: str | None
    created_by: str | None
    last_error: str | None
    result: dict[str, Any] | None

    @classmethod
    def of(cls, view: JobView) -> "AdminJobOut":
        return cls(
            id=view.id,
            kind=view.kind,
            status=view.status,
            attempts=view.attempts,
            max_attempts=view.max_attempts,
            created_at=view.created_at,
            started_at=view.started_at,
            finished_at=view.finished_at,
            customer_id=view.customer_id,
            created_by=view.created_by,
            last_error=view.last_error,
            result=view.result,
        )


class AdminJobPageOut(BaseModel):
    items: list[AdminJobOut]
    total: int
    kinds: list[str] = Field(description="Every kind a stored job has, for the filter")
