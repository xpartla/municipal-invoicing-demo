"""Header signatures and mapping suggestions (plan §9.2 step 2).

A file's header signature is its normalised header names (case, diacritics, punctuation and
spacing folded away), sorted, hashed: the same export gives the same signature whatever its
column order, so a saved template can be chosen for it automatically.

Without a template, each target field is matched to a header by the field's synonyms: a
header equal to a synonym beats one containing all its words, which beats one whose words
the synonym contains; earlier synonyms win ties. Every column serves one field. When a
column holds composite keys (`"637005 41 01 110 000"`, `"518 001"`), the key's parts
are suggested from it through `split` first. Each suggested field gets the
transforms its kind needs: trim, and zero padding for fixed-width codes.
"""

import hashlib
import re
from collections.abc import Iterable

from riso.exchange.domain.mapping import (
    SCHEMAS,
    ColumnMapping,
    FieldKind,
    FieldSource,
    ImportType,
    Split,
    TargetField,
    Transform,
    Trim,
    ZeroPad,
)
from riso.exchange.domain.table import Table, cell_text
from riso.text import fold

_NOT_WORD = re.compile(r"[^0-9a-z]+")
SAMPLE = 20
"""How many filled cells of a column the composite-key check looks at."""

_BUDGET_KEY = re.compile(r"\d{6} [0-9][0-9A-Za-z]{1,3}( \d{2} \d{3})? \d{3}")
_ACCOUNT_KEY = re.compile(r"\d{3} \d{3}")


def normalise_header(text: str) -> str:
    """`" Typ  účtu: "` → `"typ uctu"`."""
    return " ".join(_NOT_WORD.sub(" ", fold(text).casefold()).split())


def header_signature(headers: Iterable[str]) -> str:
    names = sorted({name for name in map(normalise_header, headers) if name})
    return hashlib.sha256("\x1f".join(names).encode()).hexdigest()[:16]


def _score(header: str, synonyms: tuple[str, ...]) -> int:
    words = set(header.split())
    best = 0
    for rank, synonym in enumerate(synonyms):
        wanted = set(synonym.split())
        if header == synonym:
            score = 300
        elif wanted <= words:
            score = 200
        elif words <= wanted:
            score = 100
        else:
            continue
        best = max(best, score - rank)
    return best


def suggested_transforms(target: TargetField) -> tuple[Transform, ...]:
    if target.kind is FieldKind.DECIMAL:
        return ()  # parsed with the separator found
    if target.kind is FieldKind.CODE and target.width:
        return (Trim(), ZeroPad(width=target.width))
    return (Trim(),)


def _samples(table: Table, index: int) -> list[str]:
    found = []
    for row in table.rows:
        text = cell_text(row.value(index))
        if text is not None:
            found.append(text)
            if len(found) >= SAMPLE:
                break
    return found


_PARTS: dict[str, Split] = {
    "ek": Split(index=0),
    "zdroj": Split(index=1),
    "oddiel": Split(index=2, count=5),
    "trieda": Split(index=3, count=5),
    "analytika": Split(index=-1),
    "su": Split(index=0, count=2),
    "au": Split(index=1, count=2),
}


def _composite(table: Table, import_type: ImportType) -> dict[str, FieldSource]:
    """Split suggestions for every key field, from the first column of composite keys."""
    if import_type.is_budget:
        pattern = _BUDGET_KEY
    elif import_type is ImportType.ACCOUNTS:
        pattern = _ACCOUNT_KEY
    else:
        return {}
    wanted = [t for t in SCHEMAS[import_type].key_fields if t.name in _PARTS]
    for column in table.columns:
        samples = _samples(table, column.index)
        if samples and all(pattern.fullmatch(" ".join(s.split())) for s in samples):
            found = {}
            for target in wanted:
                transforms: list[Transform] = [Trim(), _PARTS[target.name]]
                if target.width:
                    transforms.append(ZeroPad(width=target.width))
                found[target.name] = FieldSource(column=column.key, transforms=tuple(transforms))
            return found
    return {}


def suggest_mapping(table: Table, import_type: ImportType) -> ColumnMapping:
    """The mapping the cells (a column of composite keys) and the headers suggest."""
    schema = SCHEMAS[import_type]
    fields = _composite(table, import_type)
    used = {source.column for source in fields.values()}
    headers = {c.key: normalise_header(c.header) for c in table.columns if c.header}
    candidates = []
    for order, target in enumerate(schema.fields):
        if target.name in fields:
            continue
        for column in table.columns:
            header = headers.get(column.key)
            score = _score(header, target.synonyms) if header and column.key not in used else 0
            if score:
                candidates.append((score, -order, -column.index, target.name, column.key))
    for _, _, _, name, key in sorted(candidates, reverse=True):
        if name not in fields and key not in used:
            target = schema.target(name)
            fields[name] = FieldSource(column=key, transforms=suggested_transforms(target))
            used.add(key)
    ordered = {name: fields[name] for name in schema.names if name in fields}
    return ColumnMapping(import_type=import_type, fields=ordered)


def resolve_columns(mapping: ColumnMapping, table: Table) -> ColumnMapping:
    """The mapping with each column reference that is not one of the table's keys replaced
    by the key of the column with the same normalised header, so a template saved for
    `Popis` reads a file headed `POPIS`. References that match nothing stay, for
    `check_against` to report."""
    by_header: dict[str, str] = {}
    for column in table.columns:
        if column.header:
            by_header.setdefault(normalise_header(column.header), column.key)
    fields = {}
    for name, source in mapping.fields.items():
        ref = source.column
        if ref is not None and not table.has_column(ref):
            ref = by_header.get(normalise_header(ref), ref)
        fields[name] = source.model_copy(update={"column": ref})
    return mapping.model_copy(update={"fields": fields})
