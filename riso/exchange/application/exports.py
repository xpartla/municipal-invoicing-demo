"""Exporting booked invoices to CSV or XLSX (plan §7.4).

The user asks for a selection or the table's current filter. `preview_export` says what the
file would hold: the booked, exported and paid invoices, how many were exported before (the
"already exported" notice) and how many are skipped. `start_export` records an `ExportRun`
with the IDs it found and queues the `export_build` job, in one transaction. The job writes
the file of those invoices still booked, exported or paid, keeps it in the customer's
storage, and records the export on each invoice (booked ones become exported; every number is
frozen), all in one transaction, as the user who asked.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from riso.exchange.application.ports import ExportWriter
from riso.exchange.application.uow import ExchangeUnitOfWork
from riso.exchange.domain.export import (
    COLUMNS,
    Cell,
    ExportFile,
    ExportFormat,
    ExportRun,
    ExportState,
)
from riso.exchange.domain.repository import ExportRunRepository
from riso.identity import Permission
from riso.invoicing import (
    ExportableInvoice,
    InvoiceFilter,
    QueriesUnitOfWork,
    Sort,
    exportable,
    record_exports,
)
from riso.jobs import JobContext, JobRegistry
from riso.shared.clock import BRATISLAVA
from riso.shared.context import RequestContext
from riso.shared.errors import NotFound, ValidationFailed
from riso.shared.ports import FileStorage

EXPORT_JOB = "export_build"
MAX_INVOICES = 10_000


class ExportUnitOfWork(ExchangeUnitOfWork, QueriesUnitOfWork, Protocol):
    """The exchange and invoicing repositories on one transaction."""

    @property
    def exports(self) -> ExportRunRepository: ...


@dataclass(frozen=True, slots=True)
class ExportScope:
    """A selection (`invoice_ids`), else the table's filter and sort."""

    invoice_ids: tuple[str, ...] | None = None
    criteria: InvoiceFilter | None = None
    sort: Sort = Sort("booking_date", descending=False)
    described: Mapping[str, Any] | None = None
    """The filter as the user gave it, kept with the run for its history."""

    def ids(self, uow: ExportUnitOfWork, customer_id: str) -> list[str]:
        if self.invoice_ids is not None:
            return list(dict.fromkeys(self.invoice_ids))
        criteria = self.criteria or InvoiceFilter()
        return uow.invoice_queries.ids(customer_id, criteria, self.sort)

    def recorded(self) -> dict[str, Any]:
        if self.invoice_ids is not None:
            return {"invoice_ids": list(self.invoice_ids)}
        return {"filter": dict(self.described or {}), "sort": _sort_text(self.sort)}


def _sort_text(sort: Sort) -> str:
    return ("-" if sort.descending else "") + sort.key


@dataclass(frozen=True, slots=True)
class ExportPreview:
    invoices: int
    """How many the file would hold (booked, exported or paid)."""
    again: int
    """How many of them were exported before."""
    skipped: int
    """How many the selection or filter found that are not booked."""


@dataclass(frozen=True, slots=True)
class ExportRunView:
    id: str
    format: str
    state: str
    scope: dict[str, Any]
    requested: int
    invoices: int
    rows: int
    again: int
    skipped: int
    file_name: str | None
    file_size: int | None
    error: str | None
    job_id: str | None
    created_at: datetime
    created_by: str | None
    updated_at: datetime

    @classmethod
    def of(cls, run: ExportRun) -> "ExportRunView":
        return cls(
            id=run.id,
            format=run.format.value,
            state=run.state.value,
            scope=dict(run.scope),
            requested=len(run.invoice_ids),
            invoices=run.invoices,
            rows=run.rows,
            again=run.again,
            skipped=len(run.skipped),
            file_name=run.file.name if run.file else None,
            file_size=run.file.size if run.file else None,
            error=run.error,
            job_id=run.job_id,
            created_at=run.created_at,
            created_by=run.created_by,
            updated_at=run.updated_at,
        )


@dataclass(frozen=True, slots=True)
class ExportPage:
    items: list[ExportRunView]
    total: int


@dataclass(frozen=True, slots=True)
class ExportedFile:
    data: bytes
    media_type: str
    name: str


def rows(invoices: Sequence[ExportableInvoice]) -> list[list[Cell]]:
    """One row per line of each booking: the header, the posting line, the budget line."""
    found: list[list[Cell]] = []
    for invoice in invoices:
        header: list[Cell] = [
            invoice.series,
            invoice.number,
            invoice.booking_date,
            invoice.supplier_name,
            invoice.supplier_ico,
            invoice.invoice_number,
            invoice.variable_symbol,
            invoice.issue_date,
            invoice.supply_date,
            invoice.due_date,
            invoice.gross,
        ]
        for post, budget in zip(invoice.coding.posting, invoice.coding.budget, strict=False):
            found.append(
                [
                    *header,
                    post.md,
                    post.dal,
                    post.amount,
                    post.text,
                    budget.key,
                    budget.ek,
                    budget.zdroj,
                    budget.oddiel,
                    budget.trieda,
                    budget.analytika,
                    budget.transfer or post.transfer,
                    budget.text,
                ]
            )
    assert all(len(row) == len(COLUMNS) for row in found)
    return found


def _require(ctx: RequestContext, customer_id: str) -> None:
    ctx.require(Permission.INVOICES_PROCESS, customer_id)


def _found(uow: ExportUnitOfWork, customer_id: str, scope: ExportScope) -> list[str]:
    ids = scope.ids(uow, customer_id)
    if len(ids) > MAX_INVOICES:
        raise ValidationFailed.on(
            "invoice_ids", f"at most {MAX_INVOICES} invoices per export", "too_many"
        )
    return ids


def preview_export(
    ctx: RequestContext, uow: ExportUnitOfWork, customer_id: str, scope: ExportScope
) -> ExportPreview:
    _require(ctx, customer_id)
    with uow:
        invoices, skipped = exportable(uow, customer_id, _found(uow, customer_id, scope))
    return ExportPreview(len(invoices), sum(i.exported_before for i in invoices), len(skipped))


def start_export(
    ctx: RequestContext,
    uow: ExportUnitOfWork,
    customer_id: str,
    export_format: ExportFormat,
    scope: ExportScope,
) -> ExportRunView:
    _require(ctx, customer_id)
    with uow:
        invoices, _ = exportable(uow, customer_id, _found(uow, customer_id, scope))
        if not invoices:
            raise ValidationFailed.on(
                "invoice_ids", "nothing to export: no booked invoice was chosen", "nothing"
            )
        run = ExportRun.new(
            uow.ids.new(),
            customer_id,
            export_format,
            scope.recorded(),
            tuple(i.id for i in invoices),
            at=uow.clock.now(),
            actor=ctx.actor_id,
        )
        uow.exports.add(run)
        job_id = uow.queue.enqueue(
            EXPORT_JOB,
            ExportPayload(
                run_id=run.id, customer_id=customer_id, real_actor_id=ctx.real_actor_id
            ).model_dump(),
            customer_id=customer_id,
            created_by=ctx.actor_id,
        )
        run.queued_as(job_id)
        uow.exports.save(run)
        uow.audit.record(
            ctx,
            "export.requested",
            target_type="export",
            target_id=run.id,
            customer_id=customer_id,
            details={"format": export_format.value, "invoices": len(invoices), "job_id": job_id},
        )
        uow.commit()
    return ExportRunView.of(run)


def list_exports(
    ctx: RequestContext, uow: ExportUnitOfWork, customer_id: str, *, page: int, size: int
) -> ExportPage:
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        found = uow.exports.list(customer_id, offset=(page - 1) * size, limit=size)
        return ExportPage([ExportRunView.of(r) for r in found], uow.exports.count(customer_id))


def get_export(
    ctx: RequestContext, uow: ExportUnitOfWork, customer_id: str, run_id: str
) -> ExportRunView:
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        return ExportRunView.of(uow.exports.get(customer_id, run_id))


def export_file(
    ctx: RequestContext,
    uow: ExportUnitOfWork,
    storage: FileStorage,
    customer_id: str,
    run_id: str,
) -> ExportedFile:
    """The export's file, as it was written. `NotFound` before it is."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        run = uow.exports.get(customer_id, run_id)
    if run.file is None:
        raise NotFound(f"export {run_id} has no file yet")
    with storage.open(run.file.storage_key) as found:
        data = found.read()
    return ExportedFile(data, run.format.media_type, run.file.name)


class ExportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    customer_id: str
    real_actor_id: str | None = None


class ExportJobs:
    """The `export_build` job."""

    def __init__(
        self,
        uow: Callable[[], ExportUnitOfWork],
        storage: FileStorage,
        writer: ExportWriter,
    ) -> None:
        self._uow = uow
        self._storage = storage
        self._writer = writer

    def register(self, registry: JobRegistry) -> JobRegistry:
        registry.register(EXPORT_JOB, ExportPayload, self.build)
        return registry

    def build(self, payload: ExportPayload, job: JobContext) -> dict[str, Any]:
        ctx = replace(
            job.request, customer_id=payload.customer_id, real_actor_id=payload.real_actor_id
        )
        _require(ctx, payload.customer_id)
        with self._uow() as uow:
            run = uow.exports.get(payload.customer_id, payload.run_id)
            if not run.awaits(job.job_id):
                return {"skipped": True}
            at = uow.clock.now()
            invoices, skipped = exportable(uow, payload.customer_id, run.invoice_ids)
            if not invoices:
                run.failed(job.job_id, "none of the invoices is booked any more", at)
                uow.exports.save(run)
                uow.commit()
                return {"invoices": 0}
            found = rows(invoices)
            data = self._writer.write(run.format, COLUMNS, found)
            stored = self._storage.put(data, owner=payload.customer_id, extension=run.format.value)
            again = record_exports(ctx, uow, payload.customer_id, [i.id for i in invoices], run.id)
            local = run.created_at.astimezone(BRATISLAVA)
            name = f"faktury-{local:%Y-%m-%d-%H%M}.{run.format.value}"
            run.finished(
                job.job_id,
                ExportFile(stored.key, stored.sha256, name, stored.size),
                invoices=len(invoices),
                rows=len(found),
                again=again,
                skipped=tuple(skipped),
                at=at,
            )
            uow.exports.save(run)
            uow.audit.record(
                ctx,
                "export.built",
                target_type="export",
                target_id=run.id,
                customer_id=payload.customer_id,
                details={"invoices": len(invoices), "rows": len(found), "again": again},
            )
            uow.commit()
        return {"invoices": run.invoices, "rows": run.rows, "again": run.again}


__all__ = [
    "EXPORT_JOB",
    "ExportJobs",
    "ExportPage",
    "ExportPayload",
    "ExportPreview",
    "ExportRunView",
    "ExportScope",
    "ExportState",
    "ExportUnitOfWork",
    "ExportedFile",
    "export_file",
    "get_export",
    "list_exports",
    "preview_export",
    "rows",
    "start_export",
]
