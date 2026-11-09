"""The `ImportRun` aggregate (plan §9.2): one file on its way to a new version of a list.

    uploaded ──map──> mapped ──dry run──> dry_run_ok | dry_run_failed ──apply──> applied
        └──────────────┴───────────────────────┴────── cancel ──────> cancelled

A dry run and an apply run as jobs. While a job is pending the run remembers its ID: the
outcome of a job the run no longer waits for (the mapping changed meanwhile, or a retry ran
it twice) is ignored, which keeps the jobs idempotent. Mapping again, or starting a new dry
run, drops the report. While an apply is pending, the run cannot be mapped or cancelled.

Applying needs a dry run without hard errors; confirmable errors (against the global lists)
need the confirmation, which the run keeps (plan §2 decision 58). When the list changed
after the dry run, the apply job sends the run back to `mapped` with the reason, for a new
dry run.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from riso.exchange.domain.mapping import ColumnMapping, ImportType
from riso.exchange.domain.report import DryRunReport
from riso.exchange.domain.table import FileFormat, ReadOptions
from riso.shared.errors import InvalidState
from riso.shared.events import DomainEvent


class RunState(StrEnum):
    UPLOADED = "uploaded"
    MAPPED = "mapped"
    DRY_RUN_OK = "dry_run_ok"
    DRY_RUN_FAILED = "dry_run_failed"
    APPLIED = "applied"
    CANCELLED = "cancelled"


TRANSITIONS: frozenset[tuple[RunState, RunState]] = frozenset(
    {
        (RunState.UPLOADED, RunState.MAPPED),
        (RunState.UPLOADED, RunState.CANCELLED),
        (RunState.MAPPED, RunState.MAPPED),
        (RunState.MAPPED, RunState.DRY_RUN_OK),
        (RunState.MAPPED, RunState.DRY_RUN_FAILED),
        (RunState.MAPPED, RunState.CANCELLED),
        (RunState.DRY_RUN_OK, RunState.MAPPED),
        (RunState.DRY_RUN_OK, RunState.APPLIED),
        (RunState.DRY_RUN_OK, RunState.CANCELLED),
        (RunState.DRY_RUN_FAILED, RunState.MAPPED),
        (RunState.DRY_RUN_FAILED, RunState.APPLIED),
        (RunState.DRY_RUN_FAILED, RunState.CANCELLED),
    }
)
"""Every allowed (from, to). Applied and cancelled are final."""


@dataclass(frozen=True, slots=True)
class ImportFile:
    """The uploaded file, kept in the customer's storage."""

    storage_key: str
    sha256: str
    name: str
    size: int
    format: FileFormat


@dataclass(frozen=True, slots=True)
class ImportRunCreated(DomainEvent):
    run_id: str
    customer_id: str | None
    import_type: ImportType
    year: int


@dataclass(frozen=True, slots=True)
class ImportApplied(DomainEvent):
    run_id: str
    customer_id: str | None
    import_type: ImportType
    year: int
    version_id: str
    errors_confirmed: bool


@dataclass(slots=True)
class ImportRun:
    id: str
    customer_id: str | None
    """None for a global list (the admin's)."""
    import_type: ImportType
    year: int
    file: ImportFile
    state: RunState
    created_at: datetime
    created_by: str | None
    updated_at: datetime
    options: ReadOptions | None = None
    mapping: ColumnMapping | None = None
    template_id: str | None = None
    report: DryRunReport | None = None
    based_on_version_id: str | None = None
    """The active version the dry run compared with; None when the list had none."""
    job_id: str | None = None
    """The dry run or apply job the run waits for."""
    applying: bool = False
    errors_confirmed: bool = False
    version_id: str | None = None
    """The version applying made."""
    last_error: str | None = None
    """Why the last apply was sent back (the list changed meanwhile)."""
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def new(
        cls,
        run_id: str,
        customer_id: str | None,
        import_type: ImportType,
        year: int,
        file: ImportFile,
        *,
        at: datetime,
        actor: str | None,
    ) -> "ImportRun":
        if import_type.is_global != (customer_id is None):
            owner = "the platform" if import_type.is_global else "a customer"
            raise InvalidState(f"{import_type} imports belong to {owner}")
        run = cls(
            id=run_id,
            customer_id=customer_id,
            import_type=import_type,
            year=year,
            file=file,
            state=RunState.UPLOADED,
            created_at=at,
            created_by=actor,
            updated_at=at,
        )
        run.events.append(ImportRunCreated(run_id, customer_id, import_type, year))
        return run

    def _go(self, state: RunState, at: datetime) -> None:
        if (self.state, state) not in TRANSITIONS:
            raise InvalidState(f"import {self.id} is {self.state}; it cannot become {state}")
        self.state = state
        self.updated_at = at

    def _not_applying(self) -> None:
        if self.applying:
            raise InvalidState(f"import {self.id} is being applied")

    @property
    def final(self) -> bool:
        return self.state in (RunState.APPLIED, RunState.CANCELLED)

    def map(
        self,
        options: ReadOptions,
        mapping: ColumnMapping,
        at: datetime,
        *,
        template_id: str | None = None,
    ) -> None:
        self._not_applying()
        if mapping.import_type is not self.import_type:
            raise InvalidState(f"a {mapping.import_type} mapping for a {self.import_type} import")
        self._go(RunState.MAPPED, at)
        self.options, self.mapping, self.template_id = options, mapping, template_id
        self.report = self.based_on_version_id = self.job_id = None
        self.errors_confirmed = False

    def start_dry_run(self, job_id: str, at: datetime) -> None:
        """A new dry run (again after one, e.g. once the global lists were fixed)."""
        self._not_applying()
        if self.mapping is None or self.options is None:
            raise InvalidState(f"import {self.id} has no mapping")
        if self.state is not RunState.MAPPED:
            self._go(RunState.MAPPED, at)
        self.report = self.based_on_version_id = None
        self.job_id, self.updated_at = job_id, at

    def awaits(self, job_id: str) -> bool:
        return self.job_id == job_id

    def record_dry_run(
        self, job_id: str, report: DryRunReport, based_on_version_id: str | None, at: datetime
    ) -> bool:
        """Stores the report of the awaited dry run. False (nothing changes) for a job the
        run no longer waits for."""
        if not self.awaits(job_id) or self.state is not RunState.MAPPED or self.applying:
            return False
        self._go(RunState.DRY_RUN_OK if report.ok else RunState.DRY_RUN_FAILED, at)
        self.report, self.based_on_version_id, self.job_id = report, based_on_version_id, None
        return True

    def request_apply(self, job_id: str, at: datetime, *, confirm_errors: bool) -> None:
        self._not_applying()
        if self.state not in (RunState.DRY_RUN_OK, RunState.DRY_RUN_FAILED) or not self.report:
            raise InvalidState(f"import {self.id} is {self.state}; run the dry run first")
        if self.report.hard_errors:
            raise InvalidState(f"import {self.id} has errors that cannot be imported")
        if not self.report.can_apply(confirm_errors=confirm_errors):
            raise InvalidState(f"import {self.id} has errors; confirm them to import anyway")
        self.applying, self.job_id = True, job_id
        self.errors_confirmed = bool(self.report.errors) and confirm_errors
        self.last_error, self.updated_at = None, at

    def applied(self, job_id: str, version_id: str, at: datetime) -> bool:
        """The awaited apply made `version_id`. False for a job the run no longer waits for."""
        if not (self.applying and self.awaits(job_id)):
            return False
        assert self.report is not None
        self._go(RunState.APPLIED, at)
        self.applying, self.job_id, self.version_id = False, None, version_id
        self.events.append(
            ImportApplied(
                self.id,
                self.customer_id,
                self.import_type,
                self.year,
                version_id,
                self.errors_confirmed,
            )
        )
        return True

    def apply_refused(self, job_id: str, reason: str, at: datetime) -> bool:
        """The awaited apply found the list or the file changed since the dry run: back to
        `mapped` with the reason, for a new dry run."""
        if not (self.applying and self.awaits(job_id)):
            return False
        self._go(RunState.MAPPED, at)
        self.applying, self.job_id, self.report = False, None, None
        self.based_on_version_id, self.errors_confirmed, self.last_error = None, False, reason
        return True

    def cancel(self, at: datetime) -> None:
        self._not_applying()
        self._go(RunState.CANCELLED, at)
        self.job_id = None
