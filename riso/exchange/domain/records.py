"""Applying a mapping to a table (plan §9.2 steps 2–3): each row becomes the target fields'
values, rows sharing a key are merged or reported, and what reading noticed is reported the
way `riso ingest` reports it, so an import of TOPSET's exports gives the committed bundle.

The result says, per row, what went wrong (`RowError`, with the row number and the field),
and gives two kinds of warning:

- `warnings` are stored with the new version, as the bundle's `IngestWarning` (codes
  `duplicate_key`, `missing_description`, `skipped_row`, with ingest's wording);
- `notices` are the run's report only (a fact the file was expected to carry is missing).

A record's `values` are ready for the code list's entry parser: the mapped fields, the row
numbers (`row` or `rows`), the aliases of a merged budget position and the type's constants.
The parser (`riso.codelists`) then checks them against the contracts.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from riso.exchange.domain.mapping import (
    ColumnMapping,
    FieldKind,
    TargetField,
    TransformError,
    as_text,
    parse_decimal,
)
from riso.exchange.domain.table import CellValue, Table, TableRow, cell_text
from riso.text import fold

ACCOUNT_TYPES = {
    "aktivny": "active",
    "active": "active",
    "pasivny": "passive",
    "passive": "passive",
    "nakladovy": "cost",
    "cost": "cost",
    "vynosovy": "revenue",
    "revenue": "revenue",
}
"""TOPSET's Slovak account types and the contract's own names."""


@dataclass(frozen=True, slots=True)
class RowError:
    row: int | None
    """None for an error about the whole file."""
    field: str | None
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class RowWarning:
    code: str
    rows: tuple[int, ...]
    message: str


@dataclass(frozen=True, slots=True)
class Record:
    key: str
    values: dict[str, Any]
    rows: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class FileFacts:
    """What the file says about itself above its header."""

    ico: str | None = None
    period: str | None = None
    """`YYYY-MM`."""


@dataclass(frozen=True, slots=True)
class MappedTable:
    records: tuple[Record, ...]
    errors: tuple[RowError, ...]
    warnings: tuple[RowWarning, ...]
    notices: tuple[RowWarning, ...]
    facts: FileFacts
    rows_read: int
    """Rows with any content below the header."""


def _convert(target: TargetField, value: CellValue) -> Any:
    """The final value of a field from what the transforms left."""
    if target.kind is FieldKind.DECIMAL:
        return parse_decimal(value)
    text = as_text(value)
    if text is None or not text.strip():
        return None
    if target.kind is FieldKind.ACCOUNT_TYPE:
        found = ACCOUNT_TYPES.get(" ".join(fold(text).casefold().split()))
        if found is None:
            raise TransformError("unknown_account_type", f"unknown account type {text!r}")
        return found
    return text


def _value(table: Table, row: TableRow, mapping: ColumnMapping, target: TargetField) -> Any:
    source = mapping.source(target.name)
    value: CellValue
    if source.column is not None:
        value = row.value(table.column(source.column).index)
    else:
        value = source.constant
    for transform in source.transforms:
        value = transform.apply(value)
    return _convert(target, value)


@dataclass
class _Group:
    record_values: dict[str, Any]
    key: str
    rows: list[int] = field(default_factory=list)
    descriptions: list[str | None] = field(default_factory=list)
    sums: dict[str, Decimal | None] = field(default_factory=dict)


def _facts(table: Table, mapping: ColumnMapping) -> tuple[FileFacts, list[RowWarning]]:
    found: dict[str, str] = {}
    notices = []
    for fact in mapping.facts:
        cells = table.preamble[fact.row - 1] if fact.row <= len(table.preamble) else ()
        text = cell_text(cells[fact.column - 1]) if fact.column <= len(cells) else None
        match = re.search(fact.pattern, text or "")
        value: str | None = None
        if match and fact.name == "ico":
            value = match["ico"].zfill(8)
        elif match:
            year, month = int(match["year"]), int(match["month"])
            value = f"{year:04d}-{month:02d}" if 1 <= month <= 12 else None
        if value is None:
            notices.append(
                RowWarning(
                    "fact_missing",
                    (fact.row,),
                    f"row {fact.row} does not give the {fact.name}; it is not checked",
                )
            )
        else:
            found[fact.name] = value
    return FileFacts(ico=found.get("ico"), period=found.get("period")), notices


def map_table(table: Table, mapping: ColumnMapping) -> MappedTable:
    """The table's rows through the mapping. `mapping.check_against(table)` must hold."""
    mapping.check_against(table)
    schema = mapping.target_schema
    rule = mapping.duplicate_rule
    key_fields = schema.key_fields
    description = schema.description
    errors: list[RowError] = []
    warnings: list[RowWarning] = []
    groups: dict[str, _Group] = {}
    skipped: list[int] = []
    rows_read = 0

    for row in table.rows:
        if row.empty:
            continue
        rows_read += 1
        values: dict[str, Any] = {}
        row_errors: list[RowError] = []
        for target in schema.fields:
            try:
                values[target.name] = _value(table, row, mapping, target)
            except TransformError as exc:
                row_errors.append(RowError(row.number, target.name, exc.code, exc.message))
        for target in schema.fields:
            unmapped = mapping.source(target.name).empty
            if values.get(target.name) is None and target.derive and unmapped:
                values[target.name] = target.derive(values)
            if values.get(target.name) is None and target.default is not None:
                values[target.name] = target.default
        if not row_errors and all(values.get(f.name) is None for f in key_fields):
            if mapping.skip_empty_key:
                skipped.append(row.number)
            else:
                errors.append(RowError(row.number, None, "missing_key", "the row has no key"))
            continue
        if not row_errors:
            row_errors = [
                RowError(row.number, target.name, "missing", "required")
                for target in schema.fields
                if target.required and values.get(target.name) is None
            ]
        if row_errors:
            errors.extend(row_errors)
            continue

        key = key_of(values, key_fields)
        group = groups.get(key)
        if group is None:
            groups[key] = _Group(
                values,
                key,
                [row.number],
                [values.get(description) if description else None],
                {f.name: values.get(f.name) for f in schema.fields if f.kind is FieldKind.DECIMAL},
            )
            continue
        if rule == "first":
            warnings.append(
                RowWarning(
                    "duplicate_key",
                    (group.rows[0], row.number),
                    f"{schema.noun} {key} appears again; the first row is kept",
                )
            )
        elif rule == "error":
            errors.append(
                RowError(
                    row.number,
                    None,
                    "duplicate_key",
                    f"{schema.noun} {key} repeats row {group.rows[0]}",
                )
            )
        else:
            group.rows.append(row.number)
            group.descriptions.append(values.get(description) if description else None)
            for name, amount in group.sums.items():
                more = values.get(name)
                if more is not None:
                    group.sums[name] = more if amount is None else amount + more

    records = []
    no_description: list[int] = []
    for group in groups.values():
        texts = list(dict.fromkeys(d for d in group.descriptions if d))
        no_description += [n for n, d in zip(group.rows, group.descriptions, strict=True) if not d]
        if len(group.rows) > 1:
            warnings.append(
                RowWarning(
                    "duplicate_key",
                    tuple(group.rows),
                    f"{group.key} appears {len(group.rows)} times; merged, keeping the "
                    f"descriptions {texts}",
                )
            )
        values = {**group.record_values, **group.sums, **schema.constants}
        if schema.row_field == "row":
            values["row"] = group.rows[0]
        elif schema.row_field == "rows":
            values["rows"] = list(group.rows)
            values["description"] = texts[0] if texts else None
            values["aliases"] = texts[1:]
        records.append(Record(group.key, values, tuple(group.rows)))

    source = mapping.source(description) if description else None
    if source is not None and source.column is not None and no_description:
        label = table.column(source.column).header or source.column
        warnings.append(
            RowWarning(
                "missing_description",
                tuple(sorted(no_description)),
                f"{len(no_description)} rows have no {label}",
            )
        )
    if skipped:
        warnings.append(
            RowWarning("skipped_row", tuple(skipped), f"{len(skipped)} rows have no key; skipped")
        )
    facts, notices = _facts(table, mapping)
    return MappedTable(
        tuple(records), tuple(errors), tuple(warnings), tuple(notices), facts, rows_read
    )


def key_of(values: dict[str, Any], key_fields: Iterable[TargetField]) -> str:
    """The key the import gives an entry: its key fields' values, joined by spaces."""
    return " ".join(str(values[f.name]) for f in key_fields if values.get(f.name) is not None)
