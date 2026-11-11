"""The customer data export (plan §10.9, §12, decision 67). An admin starts a `data_export`
job for one customer; the job writes a ZIP of every row with the customer's ID in every table
(`tables/<table>.json`), the customer and its provider, its members' accounts without
credentials, and the files its documents, imports and exports keep (`files/<key>`), with a
`manifest.json`; it keeps the ZIP in the store and audits it, and the admin downloads it from
Úlohy. It works for a soft-deleted customer too, before a purge."""

import io
import json
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from riso.identity import Permission
from riso.jobs import JobContext, JobQueue, JobRegistry
from riso.shared.clock import local_date
from riso.shared.context import RequestContext
from riso.shared.errors import InvalidState, NotFound
from riso.shared.ports import AuditRecorder, FileStorage
from riso.shared.uow import UnitOfWork

DATA_EXPORT_JOB = "data_export"


class DataExportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    real_actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class CustomerData:
    customer_id: str
    label: str
    """What names the file: the customer's IČO."""
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    """Table → its rows as JSON values."""
    file_keys: tuple[str, ...] = ()
    """The stored files the rows name."""


class CustomerDump(Protocol):
    def exists(self, customer_id: str) -> bool:
        """Whether the customer is there, deleted or not (not purged)."""
        ...

    def read(self, customer_id: str) -> CustomerData: ...


class DataExportUnitOfWork(UnitOfWork, Protocol):
    @property
    def customer_dump(self) -> CustomerDump: ...

    @property
    def queue(self) -> JobQueue: ...

    @property
    def audit(self) -> AuditRecorder: ...


def start_data_export(ctx: RequestContext, uow: DataExportUnitOfWork, customer_id: str) -> str:
    """Queues the export and returns the job's ID."""
    ctx.require(Permission.CUSTOMER_DATA_EXPORT)
    with uow:
        if not uow.customer_dump.exists(customer_id):
            raise NotFound(f"no customer {customer_id}")
        payload = DataExportPayload(customer_id=customer_id, real_actor_id=ctx.real_actor_id)
        job_id = uow.queue.enqueue(
            DATA_EXPORT_JOB,
            payload.model_dump(),
            customer_id=customer_id,
            created_by=ctx.actor_id,
        )
        uow.audit.record(
            ctx,
            "customer.data_export_started",
            target_type="job",
            target_id=job_id,
            customer_id=customer_id,
        )
        uow.commit()
    return job_id


def write_zip(data: CustomerData, storage: FileStorage) -> tuple[bytes, int]:
    """The ZIP and how many files it holds (a key whose file is gone is listed only in the
    manifest)."""
    out = io.BytesIO()
    files = 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, rows in sorted(data.tables.items()):
            archive.writestr(
                f"tables/{name}.json",
                json.dumps(rows, ensure_ascii=False, indent=1, sort_keys=True),
            )
        for key in data.file_keys:
            if storage.exists(key):
                with storage.open(key) as source:
                    archive.writestr(f"files/{key}", source.read())
                files += 1
        manifest = {
            "customer_id": data.customer_id,
            "tables": {name: len(rows) for name, rows in sorted(data.tables.items())},
            "files": list(data.file_keys),
        }
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    return out.getvalue(), files


class DataExportJobs:
    """The `data_export` job."""

    def __init__(self, uow: Callable[[], DataExportUnitOfWork], storage: FileStorage) -> None:
        self._uow = uow
        self._storage = storage

    def register(self, registry: JobRegistry) -> JobRegistry:
        registry.register(DATA_EXPORT_JOB, DataExportPayload, self.build)
        return registry

    def build(self, payload: DataExportPayload, job: JobContext) -> dict[str, Any]:
        ctx = replace(job.request, real_actor_id=payload.real_actor_id)
        ctx.require(Permission.CUSTOMER_DATA_EXPORT)
        with self._uow() as uow:
            if not uow.customer_dump.exists(payload.customer_id):
                raise InvalidState(f"customer {payload.customer_id} is gone")
            data = uow.customer_dump.read(payload.customer_id)
            content, files = write_zip(data, self._storage)
            stored = self._storage.put(content, owner=payload.customer_id, extension="zip")
            at = uow.clock.now()
            uow.audit.record(
                ctx,
                "customer.data_exported",
                target_type="job",
                target_id=job.job_id,
                customer_id=payload.customer_id,
                details={"files": files, "size": stored.size},
            )
            uow.commit()
        return {
            "file_key": stored.key,
            "name": f"riso-udaje-{data.label}-{local_date(at):%Y-%m-%d}.zip",
            "size": stored.size,
            "tables": {name: len(rows) for name, rows in data.tables.items()},
            "files": files,
        }
