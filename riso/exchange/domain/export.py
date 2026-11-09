"""Exports of booked invoices (plan §7.4): the `ExportRun` aggregate, the layout of the file
and the spreadsheet formula guard.

    queued ──(the export_build job)──> done | failed

A run is asked for with a selection or a filter of the invoice table; the IDs it found are
kept, and the job writes the file of those still booked, exported or paid when it runs. The
file stays in the customer's storage. The job is idempotent: a run that is not queued, or a
job the run no longer waits for, changes nothing.

The layout is one row per line of the booking: the invoice's header, the posting line
(MD, DAL, amount, text) and the budget line with its key's five parts (plan §7.4).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from riso.shared.errors import InvalidState
from riso.shared.events import DomainEvent


class ExportFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"

    @property
    def media_type(self) -> str:
        if self is ExportFormat.CSV:
            return "text/csv; charset=utf-8"
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ExportState(StrEnum):
    QUEUED = "queued"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Column:
    header: str
    kind: Literal["text", "number", "date"] = "text"


COLUMNS: tuple[Column, ...] = (
    Column("Rad"),
    Column("Číslo dokladu"),
    Column("Dátum zaúčtovania", "date"),
    Column("Dodávateľ"),
    Column("IČO"),
    Column("Číslo faktúry"),
    Column("VS"),
    Column("Dátum vystavenia", "date"),
    Column("Dátum dodania", "date"),
    Column("Dátum splatnosti", "date"),
    Column("Suma faktúry", "number"),
    Column("MD"),
    Column("DAL"),
    Column("Suma", "number"),
    Column("Text zaúčtovania"),
    Column("Rozpočtová položka"),
    Column("EK"),
    Column("Zdroj"),
    Column("Oddiel"),
    Column("Trieda"),
    Column("Analytika"),
    Column("Transfer"),
    Column("Text rozpočtu"),
)
"""The file's columns, in Slovak for Slovak Excel; numbers and dates are typed."""

Cell = str | Decimal | date | None

FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def guard(text: str) -> str:
    """A text cell a spreadsheet would read as a formula gets a leading apostrophe (plan §7.4,
    §12). Amounts are numbers, never guarded, so a credit note's minus stays a minus."""
    return "'" + text if text.startswith(FORMULA_STARTS) else text


@dataclass(frozen=True, slots=True)
class ExportFile:
    storage_key: str
    sha256: str
    name: str
    size: int


@dataclass(frozen=True, slots=True)
class ExportRequested(DomainEvent):
    run_id: str
    customer_id: str
    invoices: int


@dataclass(slots=True)
class ExportRun:
    id: str
    customer_id: str
    format: ExportFormat
    scope: Mapping[str, Any]
    """What was asked for: `{"invoice_ids": […]}` or `{"filter": {…}, "sort": …}`."""
    invoice_ids: tuple[str, ...]
    state: ExportState
    created_at: datetime
    created_by: str | None
    updated_at: datetime
    job_id: str | None = None
    file: ExportFile | None = None
    invoices: int = 0
    """How many invoices the file has."""
    rows: int = 0
    again: int = 0
    """How many of them had been exported before."""
    skipped: tuple[str, ...] = ()
    """The IDs found that were not booked when the file was written."""
    error: str | None = None
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def new(
        cls,
        run_id: str,
        customer_id: str,
        export_format: ExportFormat,
        scope: Mapping[str, Any],
        invoice_ids: tuple[str, ...],
        *,
        at: datetime,
        actor: str | None,
    ) -> "ExportRun":
        if not invoice_ids:
            raise InvalidState("an export needs at least one invoice")
        run = cls(
            run_id,
            customer_id,
            export_format,
            dict(scope),
            invoice_ids,
            ExportState.QUEUED,
            at,
            actor,
            at,
        )
        run.events.append(ExportRequested(run_id, customer_id, len(invoice_ids)))
        return run

    def queued_as(self, job_id: str) -> None:
        self.job_id = job_id

    def awaits(self, job_id: str) -> bool:
        return self.state is ExportState.QUEUED and self.job_id == job_id

    def finished(
        self,
        job_id: str,
        file: ExportFile,
        *,
        invoices: int,
        rows: int,
        again: int,
        skipped: tuple[str, ...],
        at: datetime,
    ) -> None:
        if not self.awaits(job_id):
            raise InvalidState(f"export {self.id} does not wait for job {job_id}")
        self.state, self.file, self.updated_at = ExportState.DONE, file, at
        self.invoices, self.rows, self.again, self.skipped = invoices, rows, again, skipped

    def failed(self, job_id: str, error: str, at: datetime) -> None:
        if not self.awaits(job_id):
            raise InvalidState(f"export {self.id} does not wait for job {job_id}")
        self.state, self.error, self.updated_at = ExportState.FAILED, error, at
