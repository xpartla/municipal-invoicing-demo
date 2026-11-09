"""The import run and template repositories on SQLAlchemy, mapped explicitly."""

from dataclasses import asdict
from typing import Any

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import Session

from riso.exchange.domain.mapping import ColumnMapping, ImportType
from riso.exchange.domain.report import DryRunReport
from riso.exchange.domain.run import ImportFile, ImportRun, RunState
from riso.exchange.domain.table import FileFormat, ReadOptions
from riso.exchange.domain.templates import MappingTemplate, TemplateScope
from riso.exchange.infrastructure.orm import ImportRunRow, MappingTemplateRow
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


def _template_owner(scope: TemplateScope, owner_id: str | None) -> ColumnElement[bool]:
    condition = MappingTemplateRow.scope == scope.value
    if scope is TemplateScope.CUSTOMER:
        return and_(condition, MappingTemplateRow.customer_id == owner_id)
    if scope is TemplateScope.PROVIDER:
        return and_(condition, MappingTemplateRow.provider_id == owner_id)
    return condition


def _template_values(template: MappingTemplate) -> dict[str, Any]:
    return {
        "scope": template.scope.value,
        "customer_id": template.owner_id if template.scope is TemplateScope.CUSTOMER else None,
        "provider_id": template.owner_id if template.scope is TemplateScope.PROVIDER else None,
        "import_type": template.import_type.value,
        "name": template.name,
        "signature": template.signature,
        "mapping": template.mapping.model_dump(mode="json"),
        "created_at": template.created_at,
        "created_by": template.created_by,
        "updated_at": template.updated_at,
    }


def _template(row: MappingTemplateRow) -> MappingTemplate:
    scope = TemplateScope(row.scope)
    return MappingTemplate(
        id=row.id,
        scope=scope,
        owner_id=row.customer_id if scope is TemplateScope.CUSTOMER else row.provider_id,
        name=row.name,
        signature=row.signature,
        mapping=ColumnMapping.model_validate(row.mapping),
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
    )


class SqlTemplateRepository:
    def __init__(self, session: Session, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow

    def add(self, template: MappingTemplate) -> None:
        if template.builtin:
            raise ValueError("built-in templates are not stored")
        self._session.add(MappingTemplateRow(id=template.id, **_template_values(template)))
        self._session.flush()
        self._uow.track(template)

    def _row(
        self, scope: TemplateScope, owner_id: str | None, template_id: str
    ) -> MappingTemplateRow:
        row = self._session.scalar(
            select(MappingTemplateRow).where(
                MappingTemplateRow.id == template_id, _template_owner(scope, owner_id)
            )
        )
        if row is None:
            raise NotFound(f"no template {template_id}")
        return row

    def save(self, template: MappingTemplate) -> None:
        row = self._row(template.scope, template.owner_id, template.id)
        for name, value in _template_values(template).items():
            setattr(row, name, value)
        self._session.flush()
        self._uow.track(template)

    def delete(self, template: MappingTemplate) -> None:
        self._session.delete(self._row(template.scope, template.owner_id, template.id))
        self._session.flush()

    def get(self, scope: TemplateScope, owner_id: str | None, template_id: str) -> MappingTemplate:
        template = _template(self._row(scope, owner_id, template_id))
        self._uow.track(template)
        return template

    def owned(self, scope: TemplateScope, owner_id: str | None) -> list[MappingTemplate]:
        rows = self._session.scalars(
            select(MappingTemplateRow)
            .where(_template_owner(scope, owner_id))
            .order_by(MappingTemplateRow.name, MappingTemplateRow.id)
        )
        return [_template(row) for row in rows]
