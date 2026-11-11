"""The customer's import and export files, for the storage listing (plan §10.7, Úložisko)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from riso.exchange.domain.repository import ExportRunRepository, ImportRunRepository
from riso.identity import Permission
from riso.shared.context import RequestContext
from riso.shared.uow import UnitOfWork

MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
}


class RunFilesUnitOfWork(UnitOfWork, Protocol):
    @property
    def imports(self) -> ImportRunRepository: ...

    @property
    def exports(self) -> ExportRunRepository: ...


@dataclass(frozen=True, slots=True)
class RunFileView:
    kind: Literal["import", "export"]
    run_id: str
    name: str
    media_type: str
    size: int
    created_at: datetime
    created_by: str | None
    detail: str
    """What the import imported (its type), or how many invoices the export holds."""


def customer_run_files(
    ctx: RequestContext, uow: RunFilesUnitOfWork, customer_id: str
) -> list[RunFileView]:
    """Every file the customer's imports and exports keep, the newest first."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    files: list[RunFileView] = []
    with uow:
        imports = uow.imports.list(customer_id, offset=0, limit=uow.imports.count(customer_id))
        exports = uow.exports.list(customer_id, offset=0, limit=uow.exports.count(customer_id))
    for run in imports:
        files.append(
            RunFileView(
                kind="import",
                run_id=run.id,
                name=run.file.name,
                media_type=MEDIA_TYPES.get(run.file.format.value, "application/octet-stream"),
                size=run.file.size,
                created_at=run.created_at,
                created_by=run.created_by,
                detail=run.import_type.value,
            )
        )
    for export in exports:
        if export.file is None:
            continue
        extension = export.file.name.rsplit(".", 1)[-1].lower()
        files.append(
            RunFileView(
                kind="export",
                run_id=export.id,
                name=export.file.name,
                media_type=MEDIA_TYPES.get(extension, "application/octet-stream"),
                size=export.file.size,
                created_at=export.created_at,
                created_by=export.created_by,
                detail=str(export.invoices),
            )
        )
    files.sort(key=lambda f: f.created_at, reverse=True)
    return files
