"""The import run repository on SQLAlchemy, mapped explicitly."""

from dataclasses import asdict
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from riso.exchange.domain.mapping import ColumnMapping, ImportType
from riso.exchange.domain.report import DryRunReport
from riso.exchange.domain.run import ImportFile, ImportRun, RunState
from riso.exchange.domain.table import FileFormat, ReadOptions
from riso.exchange.infrastructure.orm import ImportRunRow
from riso.shared.errors import NotFound
from riso.shared.uow import UnitOfWork


def _owned_by(customer_id: str | None) -> ColumnElement[bool]:
    if customer_id is None:
        return ImportRunRow.customer_id.is_(None)
    return ImportRunRow.customer_id == customer_id


def _values(run: ImportRun) -> dict[str, Any]:
    return {
        "customer_id": run.customer_id,
        "import_type": run.import_type.value,
        "year": run.year,
        "state": run.state.value,
        "file_key": run.file.storage_key,
        "file_sha256": run.file.sha256,
        "file_name": run.file.name,
        "file_size": run.file.size,
        "file_format": run.file.format.value,
        "options": asdict(run.options) if run.options else None,
        "mapping": run.mapping.model_dump(mode="json") if run.mapping else None,
        "template_id": run.template_id,
        "report": run.report.model_dump(mode="json") if run.report else None,
        "based_on_version_id": run.based_on_version_id,
        "job_id": run.job_id,
        "applying": run.applying,
        "errors_confirmed": run.errors_confirmed,
        "version_id": run.version_id,
        "last_error": run.last_error,
        "created_at": run.created_at,
        "created_by": run.created_by,
        "updated_at": run.updated_at,
    }


def _run(row: ImportRunRow) -> ImportRun:
    return ImportRun(
        id=row.id,
        customer_id=row.customer_id,
        import_type=ImportType(row.import_type),
        year=row.year,
        file=ImportFile(
            row.file_key, row.file_sha256, row.file_name, row.file_size, FileFormat(row.file_format)
        ),
        state=RunState(row.state),
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        options=ReadOptions(**row.options) if row.options else None,
        mapping=ColumnMapping.model_validate(row.mapping) if row.mapping else None,
        template_id=row.template_id,
        report=DryRunReport.model_validate(row.report) if row.report else None,
        based_on_version_id=row.based_on_version_id,
        job_id=row.job_id,
        applying=row.applying,
        errors_confirmed=row.errors_confirmed,
        version_id=row.version_id,
        last_error=row.last_error,
    )


class SqlImportRunRepository:
    def __init__(self, session: Session, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow

    def add(self, run: ImportRun) -> None:
        self._session.add(ImportRunRow(id=run.id, **_values(run)))
        self._session.flush()
        self._uow.track(run)

    def save(self, run: ImportRun) -> None:
        row = self._row(run.customer_id, run.id)
        for name, value in _values(run).items():
            setattr(row, name, value)
        self._session.flush()
        self._uow.track(run)

    def _row(self, customer_id: str | None, run_id: str) -> ImportRunRow:
        row = self._session.scalar(
            select(ImportRunRow).where(ImportRunRow.id == run_id, _owned_by(customer_id))
        )
        if row is None:
            raise NotFound(f"no import {run_id}")
        return row

    def get(self, customer_id: str | None, run_id: str) -> ImportRun:
        run = _run(self._row(customer_id, run_id))
        self._uow.track(run)
        return run

    def list(self, customer_id: str | None, *, offset: int, limit: int) -> list[ImportRun]:
        rows = self._session.scalars(
            select(ImportRunRow)
            .where(_owned_by(customer_id))
            .order_by(ImportRunRow.created_at.desc(), ImportRunRow.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return [_run(row) for row in rows]

    def count(self, customer_id: str | None) -> int:
        return (
            self._session.scalar(
                select(func.count()).select_from(ImportRunRow).where(_owned_by(customer_id))
            )
            or 0
        )
