"""Column mappings (plan §9.2 step 2): how the columns of a read file become the fields of an
import's target, stored as JSON.

Each target field gets a column, a constant or nothing, and a list of transforms applied in
order. The transform vocabulary is small and declarative, never a script:

- `trim`: surrounding whitespace removed;
- `zero_pad`: digits padded with leading zeros to a width (`1` → `001`);
- `split`: one part of a composite value, split by a pattern (`"637005 41 01 110 000"` into
  its five parts, `"518 001"` into SU and AU); `count` takes the part only when the value
  has exactly that many parts, so an income key without the function (`"312001 41 000"`)
  leaves oddiel and trieda empty;
- `decimal`: a number with a decimal comma or point, spaces as thousands separators;
- `date`: a date in one of a few formats;
- `map`: values replaced through a table (`A` → `active`).

Row options: rows whose key fields are all empty are skipped (with a warning), and rows that
repeat a key are merged into one with the further descriptions as aliases (budgets, as
`riso ingest` does), keep the first, or are errors. Past bookings have one row per line:
rows sharing the supplier's IČO and the document number are the lines of one booking.

Facts: TOPSET writes the period and the IČO in a title row above the header; a mapping can
read them from there (`Fact`), so the import can check the file belongs to the customer.

Each import type has a target schema (`SCHEMAS`): its fields, which are required, which form
the key, and the synonyms suggestions match headers against. The fields are the code list
entries' (`riso.codelists`), checked by a test.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from riso.exchange.domain.table import HEADER_SCAN, MAX_COLUMNS, CellValue, Table, cell_text
from riso.shared.errors import FieldError, ValidationFailed
from riso.text import fold

# Import types and their targets -------------------------------------------------------------


class ImportType(StrEnum):
    """What an import makes. The list types share their names with the code list kinds."""

    ACCOUNTS = "accounts"
    BUDGET_EXPENSE = "budget_expense"
    BUDGET_INCOME = "budget_income"
    DOCUMENT_SERIES = "document_series"
    TRANSFERS = "transfers"
    COST_CENTRES = "cost_centres"
    EK = "ek"
    COFOG = "cofog"
    FUNDING_SOURCES = "funding_sources"
    FRAMEWORK_ACCOUNTS = "framework_accounts"
    PAST_BOOKINGS = "past_bookings"
    """A book of received invoices (kniha došlých faktúr): supplier precedents, not a list."""

    @property
    def is_global(self) -> bool:
        return self in GLOBAL_TYPES

    @property
    def makes_list(self) -> bool:
        """Whether applying makes a code list version (every type but past bookings)."""
        return self is not ImportType.PAST_BOOKINGS

    @property
    def is_budget(self) -> bool:
        return self in (ImportType.BUDGET_EXPENSE, ImportType.BUDGET_INCOME)


GLOBAL_TYPES = frozenset(
    {ImportType.EK, ImportType.COFOG, ImportType.FUNDING_SOURCES, ImportType.FRAMEWORK_ACCOUNTS}
)


class FieldKind(StrEnum):
    CODE = "code"
    """Text that must match a code pattern (checked by the code list's contract)."""
    TEXT = "text"
    DECIMAL = "decimal"
    DATE = "date"
    ACCOUNT_TYPE = "account_type"


Derive = Callable[[Mapping[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class TargetField:
    name: str
    kind: FieldKind
    required: bool = False
    key: bool = False
    """Part of the entry's key, in the schema's order."""
    width: int | None = None
    """The digits of a fixed-width code, for the suggested `zero_pad`."""
    synonyms: tuple[str, ...] = ()
    """Header words that suggest this field, in Slovak and English."""
    derive: Derive | None = None
    """The value when the field is not mapped, from the row's other fields."""
    default: Any = None
    """The value when the field is empty."""


@dataclass(frozen=True, slots=True)
class TargetSchema:
    type: ImportType
    fields: tuple[TargetField, ...]
    noun: str
    """What one row is, for the warnings' wording: 'account', 'code'."""
    row_field: Literal["row", "rows"] | None = None
    """Where the entry keeps its row numbers."""
    duplicates: "Duplicates" = "first"
    description: str | None = None
    """The field whose emptiness the `missing_description` warning reports."""
    constants: Mapping[str, Any] = field(default_factory=dict)
    """Fields every entry of the type gets (an imported transfer is not a mock)."""
    line_fields: tuple[str, ...] = ()
    """The fields each row gives one line of (past bookings); the others are the record's,
    from its first row."""

    def target(self, name: str) -> TargetField:
        for target in self.fields:
            if target.name == name:
                return target
        raise KeyError(name)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)

    @property
    def key_fields(self) -> tuple[TargetField, ...]:
        return tuple(f for f in self.fields if f.key)


Duplicates = Literal["merge", "first", "error", "lines"]

_DESCRIPTION = ("popis", "nazov", "text", "pomenovanie", "description", "name")
_NAME = ("nazov", "popis", "text", "pomenovanie", "name", "description")


def _budget_fields(*, expense: bool) -> tuple[TargetField, ...]:
    return (
        TargetField(
            "ek",
            FieldKind.CODE,
            required=True,
            key=True,
            width=6,
            synonyms=("ek", "kod", "kod ek", "ekonomicka klasifikacia", "polozka", "economic"),
        ),
        TargetField(
            "zdroj",
            FieldKind.CODE,
            required=True,
            key=True,
            synonyms=("zdroj", "zdroj financovania", "source", "funding source"),
        ),
        TargetField(
            "oddiel",
            FieldKind.CODE,
            required=expense,
            key=True,
            width=2,
            synonyms=("oddiel", "funkcia oddiel", "division"),
        ),
        TargetField(
            "trieda",
            FieldKind.CODE,
            required=expense,
            key=True,
            width=3,
            synonyms=("trieda", "funkcia trieda", "class"),
        ),
        TargetField(
            "analytika",
            FieldKind.CODE,
            required=True,
            key=True,
            width=3,
            synonyms=("analytika", "analytic", "analytics"),
        ),
        TargetField("description", FieldKind.TEXT, synonyms=_DESCRIPTION),
        TargetField(
            "approved",
            FieldKind.DECIMAL,
            synonyms=("schvaleny rozpocet", "schvaleny", "rozpocet", "approved", "budget"),
        ),
        TargetField(
            "adjusted",
            FieldKind.DECIMAL,
            synonyms=("upraveny rozpocet", "upraveny", "adjusted"),
        ),
    )


def _series_code(values: Mapping[str, Any]) -> Any:
    pattern = values.get("pattern")
    return pattern.split("/")[0] if isinstance(pattern, str) else None


def _code_name(type_: ImportType, noun: str) -> TargetSchema:
    return TargetSchema(
        type_,
        (
            TargetField(
                "code",
                FieldKind.CODE,
                required=True,
                key=True,
                synonyms=("kod", "code", "cislo", "polozka", "ucet"),
            ),
            TargetField("name", FieldKind.TEXT, required=True, synonyms=_NAME),
        ),
        noun,
    )


SCHEMAS: dict[ImportType, TargetSchema] = {
    ImportType.ACCOUNTS: TargetSchema(
        ImportType.ACCOUNTS,
        (
            TargetField(
                "su",
                FieldKind.CODE,
                required=True,
                key=True,
                width=3,
                synonyms=("su", "syntetika", "synteticky ucet", "synt ucet", "synthetic"),
            ),
            TargetField(
                "au",
                FieldKind.CODE,
                required=True,
                key=True,
                width=3,
                synonyms=("au", "analytika", "analyticky ucet", "anal ucet", "analytic"),
            ),
            TargetField(
                "type",
                FieldKind.ACCOUNT_TYPE,
                required=True,
                synonyms=("typ uctu", "typ", "druh uctu", "account type", "type"),
            ),
            TargetField("activity", FieldKind.TEXT, synonyms=("cinnost", "activity")),
            TargetField("description", FieldKind.TEXT, synonyms=_DESCRIPTION),
        ),
        "account",
        row_field="row",
        description="description",
    ),
    ImportType.BUDGET_EXPENSE: TargetSchema(
        ImportType.BUDGET_EXPENSE,
        _budget_fields(expense=True),
        "position",
        row_field="rows",
        duplicates="merge",
        description="description",
    ),
    ImportType.BUDGET_INCOME: TargetSchema(
        ImportType.BUDGET_INCOME,
        _budget_fields(expense=False),
        "position",
        row_field="rows",
        duplicates="merge",
        description="description",
    ),
    ImportType.DOCUMENT_SERIES: TargetSchema(
        ImportType.DOCUMENT_SERIES,
        (
            TargetField(
                "series_id",
                FieldKind.TEXT,
                synonyms=("evidencne cislo", "ev cislo", "series id", "id"),
                default="",
            ),
            TargetField(
                "pattern",
                FieldKind.TEXT,
                required=True,
                synonyms=("vzor dokladu", "vzor", "maska", "pattern", "format"),
            ),
            TargetField(
                "code",
                FieldKind.TEXT,
                required=True,
                key=True,
                synonyms=("rada", "kod rady", "prefix", "code"),
                derive=_series_code,
            ),
            TargetField("description", FieldKind.TEXT, synonyms=_DESCRIPTION, default=""),
            TargetField(
                "bank_account",
                FieldKind.TEXT,
                synonyms=("bankovy ucet", "iban", "bank account", "ucet"),
            ),
        ),
        "series",
    ),
    ImportType.TRANSFERS: TargetSchema(
        ImportType.TRANSFERS,
        (
            TargetField(
                "id",
                FieldKind.TEXT,
                required=True,
                key=True,
                synonyms=("kluc", "polozka", "kod", "id", "key"),
            ),
            TargetField("name", FieldKind.TEXT, required=True, synonyms=_NAME),
            TargetField(
                "zdroj",
                FieldKind.CODE,
                required=True,
                synonyms=("zdroj", "zdroj financovania", "source"),
            ),
        ),
        "transfer",
        constants={"mock": False},
    ),
    ImportType.COST_CENTRES: TargetSchema(
        ImportType.COST_CENTRES,
        (
            TargetField(
                "code",
                FieldKind.TEXT,
                required=True,
                key=True,
                synonyms=("stredisko", "kod", "code", "cost centre", "cost center"),
            ),
            TargetField("name", FieldKind.TEXT, required=True, synonyms=_NAME),
        ),
        "cost centre",
    ),
    ImportType.EK: _code_name(ImportType.EK, "code"),
    ImportType.COFOG: _code_name(ImportType.COFOG, "code"),
    ImportType.FUNDING_SOURCES: _code_name(ImportType.FUNDING_SOURCES, "code"),
    ImportType.FRAMEWORK_ACCOUNTS: _code_name(ImportType.FRAMEWORK_ACCOUNTS, "code"),
    ImportType.PAST_BOOKINGS: TargetSchema(
        ImportType.PAST_BOOKINGS,
        (
            TargetField(
                "supplier_ico",
                FieldKind.CODE,
                required=True,
                key=True,
                width=8,
                synonyms=("ico dodavatela", "ico", "ico partnera", "supplier ico", "company id"),
            ),
            TargetField(
                "document_number",
                FieldKind.TEXT,
                required=True,
                key=True,
                synonyms=(
                    "cislo dokladu",
                    "doklad",
                    "interne cislo",
                    "evidencne cislo",
                    "document number",
                    "document",
                ),
            ),
            TargetField(
                "supplier_name",
                FieldKind.TEXT,
                synonyms=(
                    "nazov dodavatela",
                    "dodavatel",
                    "obchodny partner",
                    "partner",
                    "supplier name",
                    "supplier",
                ),
            ),
            TargetField(
                "booking_date",
                FieldKind.DATE,
                synonyms=(
                    "datum zauctovania",
                    "datum uctovania",
                    "datum prijatia",
                    "datum",
                    "booking date",
                    "date",
                ),
            ),
            TargetField(
                "amount",
                FieldKind.DECIMAL,
                synonyms=("suma", "suma celkom", "celkom", "spolu", "amount", "total"),
            ),
            TargetField(
                "variable_symbol",
                FieldKind.TEXT,
                synonyms=("variabilny symbol", "vs", "variable symbol"),
            ),
            TargetField(
                "budget_key",
                FieldKind.CODE,
                required=True,
                synonyms=(
                    "rozpoctova polozka",
                    "rozpoctova klasifikacia",
                    "rozpocet",
                    "budget key",
                    "budget",
                ),
            ),
            TargetField("md", FieldKind.CODE, required=True, synonyms=("md", "ma dat", "debit")),
            TargetField("dal", FieldKind.CODE, required=True, synonyms=("dal", "credit")),
            TargetField(
                "budget_text",
                FieldKind.TEXT,
                synonyms=("text rozpoctu", "text polozky", "budget text"),
            ),
            TargetField(
                "posting_text",
                FieldKind.TEXT,
                synonyms=("text uctovania", "text", "popis", "posting text", "description"),
            ),
        ),
        "booking",
        row_field="rows",
        duplicates="lines",
        line_fields=("budget_key", "md", "dal", "budget_text", "posting_text"),
    ),
}
assert set(SCHEMAS) == set(ImportType)


# Transforms ---------------------------------------------------------------------------------


class TransformError(ValueError):
    """A value a transform cannot handle. `code` names the reason for the UI."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def as_text(value: CellValue) -> str | None:
    """A value as text without trimming it (`cell_text` trims); None stays None."""
    if value is None or isinstance(value, str):
        return value
    return cell_text(value)


class _Transform(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Trim(_Transform):
    op: Literal["trim"] = "trim"

    def apply(self, value: CellValue) -> CellValue:
        text = as_text(value)
        return (text.strip() or None) if text is not None else None


class ZeroPad(_Transform):
    op: Literal["zero_pad"] = "zero_pad"
    width: int = Field(ge=1, le=12)

    def apply(self, value: CellValue) -> CellValue:
        text = as_text(value)
        if text is not None and text.isdigit() and text.isascii():
            return text.zfill(self.width)
        return text


class Split(_Transform):
    op: Literal["split"] = "split"
    separator: str = Field(default=r"\s+", min_length=1, max_length=50)
    """A regular expression."""
    index: int = Field(ge=-20, le=19)
    """0-based; negative counts from the end."""
    count: int | None = Field(default=None, ge=1, le=20)
    """Take the part only when the value has exactly this many parts."""

    @field_validator("separator")
    @classmethod
    def _compiles(cls, separator: str) -> str:
        try:
            re.compile(separator)
        except re.error as exc:
            raise ValueError(f"not a valid pattern: {exc}") from None
        return separator

    def apply(self, value: CellValue) -> CellValue:
        text = as_text(value)
        if text is None:
            return None
        parts = [part for part in re.split(self.separator, text.strip()) if part]
        if self.count is not None and len(parts) != self.count:
            return None
        if not -len(parts) <= self.index < len(parts):
            return None
        return parts[self.index]


_SPACES = re.compile(r"[\s  ']")
_PLAIN_NUMBER = re.compile(r"[-+]?\d+(\.\d+)?")


class DecimalNumber(_Transform):
    op: Literal["decimal"] = "decimal"
    separator: Literal["auto", ",", "."] = "auto"
    """The decimal separator; `auto` takes the last of `,` and `.` when both appear, and a
    lone one unless it repeats (then it separates thousands)."""

    def apply(self, value: CellValue) -> CellValue:
        return parse_decimal(value, self.separator)


def parse_decimal(
    value: CellValue, separator: Literal["auto", ",", "."] = "auto"
) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool | date):
        raise TransformError("not_a_number", f"{cell_text(value)!r} is not a number")
    if isinstance(value, int | Decimal):
        return Decimal(value)
    text = _SPACES.sub("", value).removesuffix("€").removesuffix("EUR")
    if not text:
        return None
    if separator == "auto":
        commas, points = text.count(","), text.count(".")
        if commas and points:
            separator = "," if text.rfind(",") > text.rfind(".") else "."
        elif commas == 1:
            separator = ","
        elif points == 1 or (not commas and not points):
            separator = "."
        else:  # one kind, repeated: thousands
            separator = "." if commas else ","
    thousands = "." if separator == "," else ","
    text = text.replace(thousands, "").replace(separator, ".")
    if not _PLAIN_NUMBER.fullmatch(text):
        raise TransformError("not_a_number", f"{value!r} is not a number")
    try:
        return Decimal(text)
    except InvalidOperation:  # pragma: no cover - the pattern already ruled it out
        raise TransformError("not_a_number", f"{value!r} is not a number") from None


DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y")
_DOTS = re.compile(r"\s*\.\s*")


class DateValue(_Transform):
    op: Literal["date"] = "date"
    formats: tuple[str, ...] = Field(default=DATE_FORMATS, min_length=1, max_length=10)
    """`strptime` formats; `1. 6. 2026` is read as `1.6.2026`."""

    def apply(self, value: CellValue) -> CellValue:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = as_text(value)
        if text is None or not text.strip():
            return None
        compact = _DOTS.sub(".", text.strip())
        for pattern in self.formats:
            try:
                return datetime.strptime(compact, pattern).date()
            except ValueError:
                continue
        raise TransformError("not_a_date", f"{text!r} is not a date")


def _key(text: str) -> str:
    return " ".join(fold(text).casefold().split())


class MapValues(_Transform):
    op: Literal["map"] = "map"
    values: dict[str, str] = Field(max_length=200)
    """Matched regardless of case, diacritics and surrounding whitespace."""
    otherwise: Literal["keep", "empty", "error"] = "keep"

    def apply(self, value: CellValue) -> CellValue:
        text = as_text(value)
        if text is None:
            return None
        table = {_key(k): v for k, v in self.values.items()}
        found = table.get(_key(text))
        if found is not None:
            return found
        if self.otherwise == "keep":
            return text
        if self.otherwise == "empty":
            return None
        raise TransformError("unmapped_value", f"{text!r} is not in the table")


Transform = Annotated[
    Trim | ZeroPad | Split | DecimalNumber | DateValue | MapValues, Field(discriminator="op")
]


# The mapping --------------------------------------------------------------------------------


class FieldSource(BaseModel):
    """Where one target field's value comes from: a column (by its key), a constant, or
    neither (the field stays empty)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    column: str | None = Field(default=None, min_length=1, max_length=200)
    constant: str | None = Field(default=None, max_length=500)
    transforms: tuple[Transform, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def _one_source(self) -> "FieldSource":
        if self.column is not None and self.constant is not None:
            raise ValueError("a column or a constant, not both")
        return self

    @property
    def empty(self) -> bool:
        return self.column is None and self.constant is None


class Fact(BaseModel):
    """A value read from a cell above the header with a pattern: `ico` (group `ico`) or
    `period` (groups `year` and `month`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["ico", "period"]
    row: int = Field(ge=1, le=HEADER_SCAN)
    column: int = Field(default=1, ge=1, le=MAX_COLUMNS)
    pattern: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _groups(self) -> "Fact":
        try:
            groups = set(re.compile(self.pattern).groupindex)
        except re.error as exc:
            raise ValueError(f"not a valid pattern: {exc}") from None
        needed = {"ico"} if self.name == "ico" else {"year", "month"}
        if not needed <= groups:
            raise ValueError(f"the pattern needs the groups {sorted(needed)}")
        return self


class ColumnMapping(BaseModel):
    """How a file's columns become an import type's fields. Stored as JSON on an import run
    and in a template."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    import_type: ImportType
    fields: dict[str, FieldSource] = Field(default_factory=dict)
    skip_empty_key: bool = True
    duplicates: Duplicates | None = None
    """None: the type's default (merge for budgets, keep the first otherwise)."""
    facts: tuple[Fact, ...] = Field(default=(), max_length=4)

    @model_validator(mode="after")
    def _fits_the_type(self) -> "ColumnMapping":
        schema = SCHEMAS[self.import_type]
        unknown = sorted(set(self.fields) - set(schema.names))
        if unknown:
            raise ValueError(f"not fields of {self.import_type.value}: {unknown}")
        if self.duplicates == "merge" and not self.import_type.is_budget:
            raise ValueError("only budget positions can be merged")
        lines = schema.duplicates == "lines"
        if self.duplicates is not None and (self.duplicates == "lines") != lines:
            raise ValueError("past bookings, and only they, group their rows into lines")
        names = [fact.name for fact in self.facts]
        if len(names) != len(set(names)):
            raise ValueError("a fact is read once")
        return self

    @property
    def target_schema(self) -> TargetSchema:
        return SCHEMAS[self.import_type]

    @property
    def duplicate_rule(self) -> Duplicates:
        return self.duplicates or self.target_schema.duplicates

    def source(self, name: str) -> FieldSource:
        return self.fields.get(name) or FieldSource()

    def check_against(self, table: Table) -> None:
        """Raises `ValidationFailed` when a column is not in the table or a required field
        has no source (and cannot be derived). A fact the file has no row for is not an
        error: reading notes it as missing."""
        errors = []
        for name, source in self.fields.items():
            if source.column is not None and not table.has_column(source.column):
                errors.append(
                    FieldError(f"fields.{name}.column", "no such column", "unknown_column")
                )
        for target in self.target_schema.fields:
            if target.required and self.source(target.name).empty and target.derive is None:
                errors.append(FieldError(f"fields.{target.name}", "required", "missing"))
        if errors:
            raise ValidationFailed("the mapping does not fit the file", errors)
