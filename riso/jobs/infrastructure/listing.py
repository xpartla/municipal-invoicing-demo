"""The admin's list of jobs on SQLAlchemy (Úlohy, plan §10.9)."""

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from riso.jobs.application.admin import JobFilter
from riso.jobs.domain import Job
from riso.jobs.infrastructure.orm import JobRow
from riso.jobs.infrastructure.repository import read_job


class SqlJobListing:
    def __init__(self, session: Session) -> None:
        self._session = session

    def page(self, where: JobFilter, *, offset: int, limit: int) -> tuple[list[Job], int]:
        found: list[ColumnElement[bool]] = []
        if where.status is not None:
            found.append(JobRow.status == where.status.value)
        if where.kind is not None:
            found.append(JobRow.kind == where.kind)
        if where.customer_id is not None:
            found.append(JobRow.customer_id == where.customer_id)
        total = self._session.scalar(select(func.count()).select_from(JobRow).where(*found))
        rows = self._session.scalars(
            select(JobRow)
            .where(*found)
            # Newest first by the UUIDv7 ID, which keeps the order of creation even when the
            # clock steps back.
            .order_by(JobRow.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return [read_job(row) for row in rows], total or 0

    def kinds(self) -> list[str]:
        return list(self._session.scalars(select(JobRow.kind).distinct().order_by(JobRow.kind)))
