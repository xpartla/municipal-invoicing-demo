"""Request and response models of the exchange API: import runs, their preview and mapping,
and mapping templates. The mapping (`ColumnMapping`) and the dry run's report
(`DryRunReport`) are the JSON the runs store, so the API passes them as they are."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from riso.exchange.application.imports import ImportPreview, ImportRunView
from riso.exchange.application.templates import TemplateView
from riso.exchange.domain.mapping import SCHEMAS, ColumnMapping, FieldKind, ImportType
from riso.exchange.domain.report import DryRunReport
from riso.exchange.domain.run import RunState
from riso.exchange.domain.table import HEADER_SCAN, ReadOptions
from riso.exchange.domain.templates import TemplateScope


class ReadOptionsIn(BaseModel):
    """How to read the file; empty fields leave the choice to the reader."""

    sheet: str | None = Field(default=None, max_length=100)
    header_row: int | None = Field(default=None, ge=0, le=HEADER_SCAN)
    encoding: Literal["utf-8", "windows-1250"] | None = None
    delimiter: Literal[";", ",", "\t", "|"] | None = None

    def options(self) -> ReadOptions:
        return ReadOptions(self.sheet, self.header_row, self.encoding, self.delimiter)

    @classmethod
    def of(cls, options: ReadOptions) -> "ReadOptionsIn":
        return cls.model_validate(
            {
                "sheet": options.sheet,
                "header_row": options.header_row,
                "encoding": options.encoding,
                "delimiter": options.delimiter,
            }
        )


class ImportFileOut(BaseModel):
    name: str
    size: int
    format: str


class ImportRunOut(BaseModel):
    id: str
    customer_id: str | None
    import_type: ImportType
    year: int
    state: RunState
    file: ImportFileOut
    created_at: datetime
    created_by: str | None
    updated_at: datetime
    options: ReadOptionsIn | None
    mapping: ColumnMapping | None
    template_id: str | None
    report: DryRunReport | None
    job_id: str | None
    """The pending dry run or apply; follow it at `…/jobs/{job_id}` for a failure."""
    applying: bool
    errors_confirmed: bool
    version_id: str | None
    last_error: str | None
    can_apply: bool
    """A dry run without hard errors; confirmable ones need `confirm_errors`."""

    @classmethod
    def of(cls, run: ImportRunView) -> "ImportRunOut":
        return cls(
            id=run.id,
            customer_id=run.customer_id,
            import_type=run.import_type,
            year=run.year,
            state=run.state,
            file=ImportFileOut(name=run.file_name, size=run.file_size, format=run.file_format),
            created_at=run.created_at,
            created_by=run.created_by,
            updated_at=run.updated_at,
            options=ReadOptionsIn.of(run.options) if run.options else None,
            mapping=run.mapping,
            template_id=run.template_id,
            report=run.report,
            job_id=run.job_id,
            applying=run.applying,
            errors_confirmed=run.errors_confirmed,
            version_id=run.version_id,
            last_error=run.last_error,
            can_apply=run.can_apply,
        )


class ImportRunPageOut(BaseModel):
    items: list[ImportRunOut]
    total: int


class ColumnOut(BaseModel):
    key: str
    """What a mapping names the column by: its header, or `#C` for an empty or repeated one."""
    header: str
    letter: str


class PreviewRowOut(BaseModel):
    number: int
    """The row's number in the file (1-based), as errors name it."""
    cells: list[str | None]


class TargetFieldOut(BaseModel):
    name: str
    kind: FieldKind
    required: bool
    key: bool
    line: bool
    """Past bookings: a field of each line rather than of the booking."""
    derived: bool
    """Filled from the other fields when not mapped (the series code from its pattern)."""


def target_fields(import_type: ImportType) -> list[TargetFieldOut]:
    schema = SCHEMAS[import_type]
    return [
        TargetFieldOut(
            name=f.name,
            kind=f.kind,
            required=f.required,
            key=f.key,
            line=f.name in schema.line_fields,
            derived=f.derive is not None,
        )
        for f in schema.fields
    ]


class ImportPreviewOut(BaseModel):
    format: str
    sheets: list[str]
    sheet: str | None
    encoding: str | None
    delimiter: str | None
    header_row: int
    columns: list[ColumnOut]
    preamble: list[list[str | None]]
    """The rows above the header (TOPSET's title rows)."""
    rows: list[PreviewRowOut]
    data_rows: int
    signature: str
    suggestion: ColumnMapping
    template_id: str | None
    template_name: str | None
    fields: list[TargetFieldOut]
    """The import type's target fields, for the mapping step."""

    @classmethod
    def of(cls, preview: ImportPreview, import_type: ImportType) -> "ImportPreviewOut":
        return cls(
            format=preview.format,
            sheets=list(preview.sheets),
            sheet=preview.sheet,
            encoding=preview.encoding,
            delimiter=preview.delimiter,
            header_row=preview.header_row,
            columns=[
                ColumnOut(key=c.key, header=c.header, letter=c.letter) for c in preview.columns
            ],
            preamble=[list(row) for row in preview.preamble],
            rows=[PreviewRowOut(number=r.number, cells=list(r.cells)) for r in preview.rows],
            data_rows=preview.data_rows,
            signature=preview.signature,
            suggestion=preview.suggestion,
            template_id=preview.template_id,
            template_name=preview.template_name,
            fields=target_fields(import_type),
        )


class MappingIn(BaseModel):
    options: ReadOptionsIn
    mapping: ColumnMapping
    template_id: str | None = Field(default=None, max_length=64)
    """The template the mapping comes from, if any (kept on the run)."""


class ApplyIn(BaseModel):
    confirm_errors: bool = False
    """"Import anyway": lets errors against the global lists through (audited)."""


class TemplateOut(BaseModel):
    id: str
    scope: TemplateScope
    owner_id: str | None
    name: str
    import_type: ImportType
    signature: str
    mapping: ColumnMapping
    builtin: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, view: TemplateView) -> "TemplateOut":
        return cls(
            id=view.id,
            scope=view.scope,
            owner_id=view.owner_id,
            name=view.name,
            import_type=view.import_type,
            signature=view.signature,
            mapping=view.mapping,
            builtin=view.builtin,
            created_at=view.created_at,
            updated_at=view.updated_at,
        )


SavableScope = Literal["customer", "provider", "global"]


class RunTemplateIn(BaseModel):
    """Save a run's mapping as a template of the scope: the customer's, its provider's, or
    global (each needs its permission, plan §5.2)."""

    scope: SavableScope
    name: str = Field(min_length=1, max_length=120)
    template_id: str | None = Field(default=None, max_length=64)
    """Overwrite this template of the scope instead of making a new one."""


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    signature: str = Field(min_length=1, max_length=64)
    mapping: ColumnMapping
