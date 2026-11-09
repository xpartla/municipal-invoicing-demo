"""Import runs (plan §9.2): upload a file, look at it and choose a mapping, run the dry run,
apply it or cancel. The dry run and the apply are jobs (`import_dry_run`, `import_apply`).

Permissions: a customer's import needs `codelists.edit` in the customer, a global list's
`codelists.global`; looking at the history needs `customer.read`. The jobs check again, with
the context of the user who started them.

The dry run reads the stored file with the run's options, applies the mapping, checks the
entries through the code lists (contracts, the year's global lists, the active version) and
writes the report. Besides the code lists' findings it reports a file naming another IČO
(an error), a file of another year (a warning), and supplier precedents naming codes the
import removes (warnings). The apply repeats the check: the list must still be at the version
the dry run compared with and the findings must still allow it; otherwise the run goes back
to `mapped` with the reason. Every write is audited.

A past-bookings import (P2-M3-T05) makes no version: its bookings are checked through the
contracts and compared with the supplier memory and the counters
(`riso.exchange.domain.bookings`), and applying writes them through the `PrecedentSink`.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict

from riso.codelists import (
    CandidateEntry,
    ImportCheck,
    ImportSource,
    ImportWarning,
    active_entries,
    apply_import,
    check_import,
)
from riso.exchange.application.ports import CustomerDirectory, PrecedentSink, TableReader
from riso.exchange.application.templates import ChosenTemplate
from riso.exchange.application.uow import ExchangeUnitOfWork
from riso.exchange.domain.bookings import BookingsPlan, parse_bookings, plan_bookings
from riso.exchange.domain.mapping import ColumnMapping, ImportType
from riso.exchange.domain.records import MappedTable, map_table
from riso.exchange.domain.report import (
    PREVIEW,
    SAMPLE,
    CounterChange,
    DryRunReport,
    EntryChangeSample,
    Issue,
    ReportDiff,
)
from riso.exchange.domain.run import ImportFile, ImportRun, RunState
from riso.exchange.domain.suggestions import header_signature, resolve_columns, suggest_mapping
from riso.exchange.domain.table import FileFormat, ReadOptions, Workbook, cell_text
from riso.identity import Permission
from riso.jobs import JobContext, JobRegistry
from riso.shared.context import RequestContext
from riso.shared.errors import ValidationFailed
from riso.shared.ports import FileStorage

DRY_RUN_JOB = "import_dry_run"
APPLY_JOB = "import_apply"
MIN_YEAR, MAX_YEAR = 2000, 2100
PREVIEW_ROWS = 10
MAX_PAGE = 200
GLOBAL_OWNER = "global"
"""The storage owner of the global lists' import files."""


def _require_edit(ctx: RequestContext, customer_id: str | None) -> None:
    if customer_id is None:
        ctx.require(Permission.GLOBAL_CODELISTS)
    else:
        ctx.require(Permission.CODELISTS_EDIT, customer_id)


def _require_read(ctx: RequestContext, customer_id: str | None) -> None:
    if customer_id is None:
        ctx.require(Permission.GLOBAL_CODELISTS)
    else:
        ctx.require(Permission.CUSTOMER_READ, customer_id)


def clean_name(name: str) -> str:
    """The file's own name: no folders, no control characters, at most 255 characters."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = "".join(c for c in base if c.isprintable()).strip()
    return base[:255] or "import"


# Views ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ImportRunView:
    id: str
    customer_id: str | None
    import_type: ImportType
    year: int
    state: RunState
    file_name: str
    file_size: int
    file_format: str
    created_at: datetime
    created_by: str | None
    updated_at: datetime
    options: ReadOptions | None
    mapping: ColumnMapping | None
    template_id: str | None
    report: DryRunReport | None
    job_id: str | None
    applying: bool
    errors_confirmed: bool
    version_id: str | None
    last_error: str | None

    @property
    def can_apply(self) -> bool:
        """A dry run without hard errors (confirmable ones need the confirmation)."""
        return (
            self.state in (RunState.DRY_RUN_OK, RunState.DRY_RUN_FAILED)
            and self.report is not None
            and not self.report.hard_errors
            and not self.applying
        )

    @classmethod
    def of(cls, run: ImportRun) -> "ImportRunView":
        return cls(
            id=run.id,
            customer_id=run.customer_id,
            import_type=run.import_type,
            year=run.year,
            state=run.state,
            file_name=run.file.name,
            file_size=run.file.size,
            file_format=run.file.format.value,
            created_at=run.created_at,
            created_by=run.created_by,
            updated_at=run.updated_at,
            options=run.options,
            mapping=run.mapping,
            template_id=run.template_id,
            report=run.report,
            job_id=run.job_id,
            applying=run.applying,
            errors_confirmed=run.errors_confirmed,
            version_id=run.version_id,
            last_error=run.last_error,
        )


@dataclass(frozen=True, slots=True)
class ColumnView:
    key: str
    header: str
    letter: str


@dataclass(frozen=True, slots=True)
class PreviewRow:
    number: int
    cells: tuple[str | None, ...]


@dataclass(frozen=True, slots=True)
class ImportPreview:
    """The file as the given options read it, with the suggested mapping."""

    format: str
    sheets: tuple[str, ...]
    sheet: str | None
    encoding: str | None
    delimiter: str | None
    header_row: int
    columns: tuple[ColumnView, ...]
    preamble: tuple[tuple[str | None, ...], ...]
    rows: tuple[PreviewRow, ...]
    data_rows: int
    signature: str
    suggestion: ColumnMapping
    template_id: str | None
    """The template the suggestion comes from; None for the headers' suggestion."""
    template_name: str | None

    @classmethod
    def of(
        cls,
        workbook: Workbook,
        suggestion: ColumnMapping,
        template_id: str | None,
        template_name: str | None,
    ) -> "ImportPreview":
        table = workbook.table
        filled = [row for row in table.rows if not row.empty][:PREVIEW_ROWS]
        return cls(
            format=workbook.format.value,
            sheets=workbook.sheets,
            sheet=workbook.sheet,
            encoding=workbook.encoding,
            delimiter=workbook.delimiter,
            header_row=table.header_row,
            columns=tuple(ColumnView(c.key, c.header, c.letter) for c in table.columns),
            preamble=tuple(tuple(cell_text(cell) for cell in row) for row in table.preamble),
            rows=tuple(
                PreviewRow(row.number, tuple(cell_text(cell) for cell in row.cells))
                for row in filled
            ),
            data_rows=table.data_rows,
            signature=header_signature(table.headers),
            suggestion=suggestion,
            template_id=template_id,
            template_name=template_name,
        )


# Commands ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UploadImport:
    customer_id: str | None
    import_type: ImportType
    year: int
    filename: str
    data: bytes


def _audit(
    uow: ExchangeUnitOfWork,
    ctx: RequestContext,
    action: str,
    run: ImportRun,
    **details: object,
) -> None:
    uow.audit.record(
        ctx,
        action,
        target_type="import_run",
        target_id=run.id,
        customer_id=run.customer_id,
        details={
            "import_type": run.import_type.value,
            "year": run.year,
            "state": run.state.value,
            **details,
        },
    )


def create_import(
    ctx: RequestContext,
    uow: ExchangeUnitOfWork,
    storage: FileStorage,
    reader: TableReader,
    cmd: UploadImport,
) -> ImportRunView:
    """Stores the file and starts a run. Refuses (`ValidationFailed`) a file that does not
    read as CSV, XLSX or XLS."""
    _require_edit(ctx, cmd.customer_id)
    if not MIN_YEAR <= cmd.year <= MAX_YEAR:
        raise ValidationFailed.on("year", f"between {MIN_YEAR} and {MAX_YEAR}", "year")
    if cmd.import_type.is_global != (cmd.customer_id is None):
        raise ValidationFailed.on("import_type", "not an import of this owner", "import_type")
    workbook = reader.read(cmd.data)
    stored = storage.put(
        cmd.data, owner=cmd.customer_id or GLOBAL_OWNER, extension=workbook.format.value
    )
    with uow:
        run = ImportRun.new(
            uow.ids.new(),
            cmd.customer_id,
            cmd.import_type,
            cmd.year,
            ImportFile(
                stored.key, stored.sha256, clean_name(cmd.filename), stored.size, workbook.format
            ),
            at=uow.clock.now(),
            actor=ctx.actor_id,
        )
        uow.imports.add(run)
        _audit(uow, ctx, "imports.uploaded", run, sha256=stored.sha256, size=stored.size)
        uow.commit()
    return ImportRunView.of(run)


def _read(
    storage: FileStorage, reader: TableReader, run: ImportRun, options: ReadOptions | None
) -> Workbook:
    with storage.open(run.file.storage_key) as handle:
        data = handle.read()
    return reader.read(data, options)


def get_import(
    ctx: RequestContext, uow: ExchangeUnitOfWork, customer_id: str | None, run_id: str
) -> ImportRunView:
    _require_read(ctx, customer_id)
    with uow:
        return ImportRunView.of(uow.imports.get(customer_id, run_id))


MEDIA_TYPES = {
    FileFormat.CSV: "text/csv",
    FileFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    FileFormat.XLS: "application/vnd.ms-excel",
}


@dataclass(frozen=True, slots=True)
class ImportFileData:
    name: str
    data: bytes
    media_type: str

    @property
    def quoted_name(self) -> str:
        """The name for a `filename*=UTF-8''…` header."""
        return quote(self.name, safe="")


def import_file(
    ctx: RequestContext,
    uow: ExchangeUnitOfWork,
    storage: FileStorage,
    customer_id: str | None,
    run_id: str,
) -> ImportFileData:
    """The run's file as it was uploaded."""
    _require_read(ctx, customer_id)
    with uow:
        run = uow.imports.get(customer_id, run_id)
    with storage.open(run.file.storage_key) as handle:
        data = handle.read()
    return ImportFileData(run.file.name, data, MEDIA_TYPES[run.file.format])


def list_imports(
    ctx: RequestContext,
    uow: ExchangeUnitOfWork,
    customer_id: str | None,
    *,
    page: int = 1,
    size: int = 50,
) -> tuple[list[ImportRunView], int]:
    """The owner's runs, the newest first, and how many there are."""
    _require_read(ctx, customer_id)
    size = max(1, min(size, MAX_PAGE))
    with uow:
        runs = uow.imports.list(customer_id, offset=(max(page, 1) - 1) * size, limit=size)
        total = uow.imports.count(customer_id)
    return [ImportRunView.of(run) for run in runs], total


def preview_import(
    ctx: RequestContext,
    uow: ExchangeUnitOfWork,
    storage: FileStorage,
    reader: TableReader,
    customer_id: str | None,
    run_id: str,
    options: ReadOptions | None = None,
    *,
    templates: Callable[[Workbook, ImportType], ChosenTemplate | None] | None = None,
) -> ImportPreview:
    """The file read with `options` (else the run's, else the readers' choices) and the
    mapping suggested for it: the run's own mapping when it fits the file, else the template
    `templates` chooses by the header signature, else the headers' suggestion."""
    _require_edit(ctx, customer_id)
    with uow:
        run = uow.imports.get(customer_id, run_id)
    workbook = _read(storage, reader, run, options or run.options)
    if run.mapping is not None:
        resolved = resolve_columns(run.mapping, workbook.table)
        try:
            resolved.check_against(workbook.table)
        except ValidationFailed:
            pass
        else:
            return ImportPreview.of(workbook, resolved, run.template_id, None)
    chosen = templates(workbook, run.import_type) if templates is not None else None
    if chosen is not None:
        return ImportPreview.of(workbook, chosen.mapping, chosen.id, chosen.name)
    return ImportPreview.of(workbook, suggest_mapping(workbook.table, run.import_type), None, None)


def set_mapping(
    ctx: RequestContext,
    uow: ExchangeUnitOfWork,
    storage: FileStorage,
    reader: TableReader,
    customer_id: str | None,
    run_id: str,
    options: ReadOptions,
    mapping: ColumnMapping,
    *,
    template_id: str | None = None,
) -> ImportRunView:
    """Saves how to read the file and map it. Refuses (`ValidationFailed`) a mapping that
    does not fit the file read with the options."""
    _require_edit(ctx, customer_id)
    with uow:
        run = uow.imports.get(customer_id, run_id)
    workbook = _read(storage, reader, run, options)
    mapping = resolve_columns(mapping, workbook.table)
    mapping.check_against(workbook.table)
    with uow:
        run = uow.imports.get(customer_id, run_id)
        run.map(workbook.options, mapping, uow.clock.now(), template_id=template_id)
        uow.imports.save(run)
        _audit(uow, ctx, "imports.mapped", run, template_id=template_id)
        uow.commit()
    return ImportRunView.of(run)


class ImportJobPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    customer_id: str | None
    real_actor_id: str | None = None


def _payload(ctx: RequestContext, run: ImportRun) -> dict[str, Any]:
    return ImportJobPayload(
        run_id=run.id, customer_id=run.customer_id, real_actor_id=ctx.real_actor_id
    ).model_dump()


def start_dry_run(
    ctx: RequestContext, uow: ExchangeUnitOfWork, customer_id: str | None, run_id: str
) -> ImportRunView:
    _require_edit(ctx, customer_id)
    with uow:
        run = uow.imports.get(customer_id, run_id)
        job_id = uow.queue.enqueue(
            DRY_RUN_JOB, _payload(ctx, run), customer_id=customer_id, created_by=ctx.actor_id
        )
        run.start_dry_run(job_id, uow.clock.now())
        uow.imports.save(run)
        _audit(uow, ctx, "imports.dry_run_started", run, job_id=job_id)
        uow.commit()
    return ImportRunView.of(run)


def request_apply(
    ctx: RequestContext,
    uow: ExchangeUnitOfWork,
    customer_id: str | None,
    run_id: str,
    *,
    confirm_errors: bool = False,
) -> ImportRunView:
    """Queues the apply. Refuses (`InvalidState`) a run without a dry run, with hard errors,
    or with errors against the global lists that `confirm_errors` does not confirm."""
    _require_edit(ctx, customer_id)
    with uow:
        run = uow.imports.get(customer_id, run_id)
        job_id = uow.queue.enqueue(
            APPLY_JOB, _payload(ctx, run), customer_id=customer_id, created_by=ctx.actor_id
        )
        run.request_apply(job_id, uow.clock.now(), confirm_errors=confirm_errors)
        uow.imports.save(run)
        confirmed = len(run.report.confirmable_errors) if run.errors_confirmed and run.report else 0
        _audit(
            uow,
            ctx,
            "imports.apply_requested",
            run,
            job_id=job_id,
            errors_confirmed=run.errors_confirmed,
            confirmed_errors=confirmed,
        )
        uow.commit()
    return ImportRunView.of(run)


def cancel_import(
    ctx: RequestContext, uow: ExchangeUnitOfWork, customer_id: str | None, run_id: str
) -> ImportRunView:
    _require_edit(ctx, customer_id)
    with uow:
        run = uow.imports.get(customer_id, run_id)
        run.cancel(uow.clock.now())
        uow.imports.save(run)
        _audit(uow, ctx, "imports.cancelled", run)
        uow.commit()
    return ImportRunView.of(run)


# The jobs ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Prepared:
    workbook: Workbook
    mapped: MappedTable


@dataclass(frozen=True, slots=True)
class _Outcome:
    report: DryRunReport
    check: ImportCheck | None = None
    """A list import's check; None for past bookings and for a file that does not read."""
    candidates: tuple[CandidateEntry, ...] = ()
    plan: BookingsPlan | None = None
    """A past-bookings import's plan."""


class ImportJobs:
    """The handlers of `import_dry_run` and `import_apply`. Both are idempotent: they act
    only for the job the run waits for."""

    def __init__(
        self,
        uow: Callable[[], ExchangeUnitOfWork],
        storage: FileStorage,
        reader: TableReader,
        precedents: PrecedentSink,
        customers: CustomerDirectory,
    ) -> None:
        self._uow = uow
        self._storage = storage
        self._reader = reader
        self._state = precedents
        self._customers = customers

    def register(self, registry: JobRegistry) -> JobRegistry:
        registry.register(DRY_RUN_JOB, ImportJobPayload, self.dry_run)
        registry.register(APPLY_JOB, ImportJobPayload, self.apply)
        return registry

    @staticmethod
    def _context(payload: ImportJobPayload, job: JobContext) -> RequestContext:
        return replace(
            job.request, customer_id=payload.customer_id, real_actor_id=payload.real_actor_id
        )

    def _prepare(self, run: ImportRun) -> _Prepared | Issue:
        assert run.mapping is not None
        try:
            workbook = _read(self._storage, self._reader, run, run.options)
            mapping = resolve_columns(run.mapping, workbook.table)
            return _Prepared(workbook, map_table(workbook.table, mapping))
        except ValidationFailed as exc:
            return Issue(severity="error", code="unreadable", message=exc.message)

    def _report(
        self, uow: ExchangeUnitOfWork, run: ImportRun, prepared: _Prepared | Issue
    ) -> _Outcome:
        now = uow.clock.now()
        if isinstance(prepared, Issue):
            return _Outcome(
                DryRunReport(checked_at=now, rows_read=0, entries=0, errors=(prepared,))
            )
        mapped = prepared.mapped
        errors = [
            Issue(
                severity="error",
                code=e.code,
                message=e.message,
                rows=(e.row,) if e.row is not None else (),
                field=e.field,
            )
            for e in mapped.errors
        ]
        warnings = [
            Issue(severity="warning", code=w.code, message=w.message, rows=w.rows)
            for w in (*mapped.warnings, *mapped.notices)
        ]
        facts = mapped.facts
        if run.customer_id is not None and facts.ico is not None:
            own = self._customers.ico_of(run.customer_id)
            if facts.ico != own:
                errors.append(
                    Issue(
                        severity="error",
                        code="other_customer",
                        message=f"the file is for IČO {facts.ico}, not {own}",
                        value=facts.ico,
                    )
                )
        if facts.period is not None and int(facts.period[:4]) != run.year:
            warnings.append(
                Issue(
                    severity="warning",
                    code="other_year",
                    message=f"the file is for {facts.period}, the import for {run.year}",
                    value=facts.period,
                )
            )
        if not run.import_type.makes_list:
            return self._bookings_report(uow, run, mapped, errors, warnings)
        candidates = tuple(CandidateEntry(r.key, r.rows, r.values) for r in mapped.records)
        rows = {c.key: c.rows for c in candidates}
        check = check_import(uow, run.customer_id, run.import_type.value, run.year, candidates)
        errors += [
            Issue(
                severity="error",
                code=p.code,
                message=f"{p.key}: {p.field + ': ' if p.field else ''}{p.message}",
                rows=p.rows,
                field=p.field,
                key=p.key,
            )
            for p in check.problems
        ]
        for finding in check.findings:
            issue = Issue(
                severity="error" if finding.severity == "error" else "warning",
                code=finding.code,
                message=finding.message,
                rows=rows.get(finding.key or "", ()),
                field=finding.field,
                key=finding.key,
                value=finding.value,
                confirmable=finding.severity == "error",
            )
            (errors if issue.severity == "error" else warnings).append(issue)
        if not check.entries and not errors:
            errors.append(Issue(severity="error", code="no_entries", message="no entries"))
        warnings += self._precedents(run, check)
        report = DryRunReport(
            checked_at=now,
            rows_read=mapped.rows_read,
            entries=len(check.entries),
            errors=tuple(errors),
            warnings=tuple(warnings),
            diff=ReportDiff(
                base_version_id=check.active.id if check.active else None,
                base_number=check.active.number if check.active else None,
                added=len(check.added),
                removed=len(check.removed),
                changed=len(check.changed),
                unchanged=check.unchanged,
                added_sample=tuple(e.values for e in check.added[:SAMPLE]),
                removed_sample=tuple(e.values for e in check.removed[:SAMPLE]),
                changed_sample=tuple(
                    EntryChangeSample(key=c.key, before=c.before.values, after=c.after.values)
                    for c in check.changed[:SAMPLE]
                ),
            ),
            preview=tuple(e.values for e in check.entries[:PREVIEW]),
            file_ico=facts.ico,
            period=facts.period,
        )
        return _Outcome(report, check, candidates)

    def _bookings_report(
        self,
        uow: ExchangeUnitOfWork,
        run: ImportRun,
        mapped: MappedTable,
        errors: list[Issue],
        warnings: list[Issue],
    ) -> _Outcome:
        """A past-bookings import: the bookings through the contracts, then compared with
        the supplier memory, the counters and the year's lists."""
        assert run.customer_id is not None
        customer_id, year = run.customer_id, run.year
        bookings, problems = parse_bookings(mapped.records)
        errors += [
            Issue(
                severity="error",
                code=p.code,
                message=f"{p.key}: {p.field + ': ' if p.field else ''}{p.message}",
                rows=p.rows,
                field=p.field,
                key=p.key,
            )
            for p in problems
        ]
        series = {
            str(e.values["code"]): str(e.values["pattern"])
            for e in active_entries(uow, customer_id, "document_series", year)
        }
        plan = plan_bookings(
            bookings,
            self._state.memory(customer_id),
            self._state.counters(customer_id),
            series=series,
            positions=frozenset(
                e.key for e in active_entries(uow, customer_id, "budget_expense", year)
            ),
            accounts=frozenset(e.key for e in active_entries(uow, customer_id, "accounts", year)),
        )
        warnings += [
            Issue(
                severity="warning",
                code=w.code,
                message=w.message,
                rows=w.rows,
                key=w.key,
                value=w.value,
            )
            for w in plan.warnings
        ]
        if not bookings and not errors:
            errors.append(Issue(severity="error", code="no_entries", message="no bookings"))
        report = DryRunReport(
            checked_at=uow.clock.now(),
            rows_read=mapped.rows_read,
            entries=len(bookings),
            errors=tuple(errors),
            warnings=tuple(warnings),
            diff=ReportDiff(
                added=len(plan.new),
                unchanged=len(plan.present),
                added_sample=tuple(b.summary() for b in plan.new[:SAMPLE]),
            ),
            preview=tuple(b.summary() for b in bookings[:PREVIEW]),
            file_ico=mapped.facts.ico,
            period=mapped.facts.period,
            counters=tuple(
                CounterChange(key=c.key, before=c.before, after=c.after) for c in plan.counters
            ),
            numbers_used=len(plan.numbers),
        )
        return _Outcome(report, plan=plan)

    def _precedents(self, run: ImportRun, check: ImportCheck) -> list[Issue]:
        """Warnings for supplier precedents naming a position or an account the import
        removes (the engine then treats them as incompatible)."""
        removed = check.removed_keys
        budget = run.import_type in (ImportType.BUDGET_EXPENSE, ImportType.BUDGET_INCOME)
        if run.customer_id is None or not removed:
            return []
        if not budget and run.import_type is not ImportType.ACCOUNTS:
            return []
        suppliers: defaultdict[str, set[str]] = defaultdict(set)
        precedents: defaultdict[str, int] = defaultdict(int)
        for supplier in self._state.memory(run.customer_id).suppliers:
            for precedent in supplier.precedents:
                codes = {
                    code
                    for line in precedent.lines
                    for code in ((line.budget_key,) if budget else (line.md, line.dal))
                    if code in removed
                }
                for code in codes:
                    suppliers[code].add(supplier.ico)
                    precedents[code] += 1
        return [
            Issue(
                severity="warning",
                code="precedent_removed_code",
                message=f"{precedents[code]} precedents of {len(suppliers[code])} suppliers "
                f"name {code}, which the import removes",
                key=code,
            )
            for code in sorted(precedents)
        ]

    def dry_run(self, payload: ImportJobPayload, job: JobContext) -> dict[str, Any]:
        ctx = self._context(payload, job)
        _require_edit(ctx, payload.customer_id)
        with self._uow() as uow:
            run = uow.imports.get(payload.customer_id, payload.run_id)
        if not run.awaits(job.job_id) or run.state is not RunState.MAPPED or run.applying:
            return {"skipped": True}
        prepared = self._prepare(run)
        with self._uow() as uow:
            run = uow.imports.get(payload.customer_id, payload.run_id)
            outcome = self._report(uow, run, prepared)
            report, check = outcome.report, outcome.check
            based_on = check.active.id if check and check.active else None
            if not run.record_dry_run(job.job_id, report, based_on, uow.clock.now()):
                return {"skipped": True}
            uow.imports.save(run)
            _audit(
                uow,
                ctx,
                "imports.dry_run_finished",
                run,
                job_id=job.job_id,
                entries=report.entries,
                errors=len(report.errors),
                warnings=len(report.warnings),
            )
            uow.commit()
        return {"state": run.state.value, "errors": len(report.errors)}

    def apply(self, payload: ImportJobPayload, job: JobContext) -> dict[str, Any]:
        ctx = self._context(payload, job)
        _require_edit(ctx, payload.customer_id)
        with self._uow() as uow:
            run = uow.imports.get(payload.customer_id, payload.run_id)
        if run.state is RunState.APPLIED:
            return {"version_id": run.version_id}
        if not (run.applying and run.awaits(job.job_id)):
            return {"skipped": True}
        prepared = self._prepare(run)
        with self._uow() as uow:
            run = uow.imports.get(payload.customer_id, payload.run_id)
            if not (run.applying and run.awaits(job.job_id)):
                return {"skipped": True}
            now = uow.clock.now()
            outcome = self._report(uow, run, prepared)
            report, check = outcome.report, outcome.check
            reason = None
            if isinstance(prepared, Issue) or (run.import_type.makes_list and check is None):
                reason = "the file no longer reads with the mapping"
            elif (
                check is not None
                and (check.active.id if check.active else None) != run.based_on_version_id
            ):
                reason = "the list changed since the dry run"
            elif not report.can_apply(confirm_errors=run.errors_confirmed):
                reason = "the findings changed since the dry run"
            if reason is not None or isinstance(prepared, Issue):
                run.apply_refused(job.job_id, reason or "refused", now)
                uow.imports.save(run)
                _audit(uow, ctx, "imports.apply_refused", run, job_id=job.job_id, reason=reason)
                uow.commit()
                return {"refused": reason}
            if outcome.plan is not None:
                return self._apply_bookings(uow, ctx, run, job.job_id, outcome.plan, report)
            version = apply_import(
                ctx,
                uow,
                run.customer_id,
                run.import_type.value,
                run.year,
                outcome.candidates,
                expected_version_id=run.based_on_version_id,
                import_run_id=run.id,
                source=ImportSource(
                    run.file.name, run.file.sha256, prepared.workbook.table.data_rows
                ),
                warnings=[
                    ImportWarning(w.code, run.file.name, w.rows, w.message)
                    for w in prepared.mapped.warnings
                ],
                period=report.period,
            )
            run.applied(job.job_id, version.id, now)
            uow.imports.save(run)
            _audit(
                uow,
                ctx,
                "imports.applied",
                run,
                job_id=job.job_id,
                version_id=version.id,
                number=version.number,
                entries=report.entries,
                errors_confirmed=run.errors_confirmed,
                confirmed_errors=len(report.confirmable_errors) if run.errors_confirmed else 0,
            )
            uow.commit()
        return {"version_id": version.id, "number": version.number}

    def _apply_bookings(
        self,
        uow: ExchangeUnitOfWork,
        ctx: RequestContext,
        run: ImportRun,
        job_id: str,
        plan: BookingsPlan,
        report: DryRunReport,
    ) -> dict[str, Any]:
        """Writes the plan through the sink, then records the run. The sink's files are
        written before the commit: a retry after a failed commit finds the bookings present
        and adds nothing twice."""
        assert run.customer_id is not None
        self._state.add(run.customer_id, plan)
        run.applied(job_id, None, uow.clock.now())
        uow.imports.save(run)
        _audit(
            uow,
            ctx,
            "imports.applied",
            run,
            job_id=job_id,
            bookings=len(plan.new),
            skipped=len(plan.present),
            numbers_used=len(plan.numbers),
            counters={c.key: c.after for c in plan.counters},
        )
        uow.commit()
        return {"bookings": len(plan.new), "skipped": len(plan.present)}
