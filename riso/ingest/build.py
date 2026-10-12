"""Stage S0: builds a ReferenceBundle from the Excel exports (plan sections 3.2 and 5).

A file that does not have the expected shape stops the build. Inside a file, a row that
cannot be read is skipped and reported, and rows sharing a budget key are merged."""

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from riso.contracts import (
    Account,
    BudgetPosition,
    DocumentSeries,
    Entity,
    IngestWarning,
    ReferenceBundle,
    SourceFile,
    Transfer,
    budget_key,
)
from riso.ingest.excel import read_rows

CHART_FILE = "UctovnyRozvrh.xls"
EXPENSE_FILE = "Vykaz_vydaj.xlsx"
INCOME_FILE = "Vykaz_prijem.xlsx"
SERIES_FILE = "Vykaz_doklady.xlsx"
EXPORT_FILES = (CHART_FILE, EXPENSE_FILE, INCOME_FILE, SERIES_FILE)

CHART_HEADER = ["SU", "AU", "Typ účtu", "Zarad. SÚV", "Zarad. VZaS", "Činnosť", "Popis"]
BUDGET_HEADER = ["Kód", "Zdroj", "Oddiel", "Trieda", "Analytika", "Popis"]
SERIES_HEADER = ["Evidenčné číslo", "Vzor dokladu", "Popis", "Bankový účet"]

# Sheet rows above the data: the chart has a title, the entity and the header.
HEADER_ROWS = {CHART_FILE: 3, EXPENSE_FILE: 1, INCOME_FILE: 1, SERIES_FILE: 1}

ACCOUNT_TYPES = {
    "Aktívny": "active",
    "Pasívny": "passive",
    "Nákladový": "cost",
    "Výnosový": "revenue",
}

_CHART_TITLE = re.compile(r"Obdobie:\s*(\d{1,2})\.\s*(\d{4})\.?\s*IČO:\s*(\d{6,8})")
_DIGITS = re.compile(r"[0-9]+")
_ZDROJ = re.compile(r"[0-9][0-9A-Za-z]{1,3}")


class IngestError(ValueError):
    """An export is missing or does not have the shape the loader knows."""


class _RowError(ValueError):
    pass


def build_bundle(raw_dir: Path) -> ReferenceBundle:
    missing = [name for name in EXPORT_FILES if not (raw_dir / name).is_file()]
    if missing:
        raise IngestError(f"missing exports in {raw_dir}: {', '.join(missing)}")
    tables = {name: read_rows(raw_dir / name) for name in EXPORT_FILES}

    warnings: list[IngestWarning] = []
    entity, period = _chart_entity(tables[CHART_FILE])
    accounts = _accounts(tables[CHART_FILE], warnings)
    expense = _budget_positions(tables[EXPENSE_FILE], EXPENSE_FILE, warnings, with_function=True)
    income = _budget_positions(tables[INCOME_FILE], INCOME_FILE, warnings, with_function=False)
    series = _document_series(tables[SERIES_FILE], warnings)
    return ReferenceBundle(
        bundle_id=f"{entity.ico}/{period}",
        entity=entity,
        period=period,
        sources=[
            SourceFile(
                name=name,
                sha256=hashlib.sha256((raw_dir / name).read_bytes()).hexdigest(),
                data_rows=len(tables[name]) - HEADER_ROWS[name],
            )
            for name in EXPORT_FILES
        ],
        accounts=accounts,
        budget_positions_expense=expense,
        budget_positions_income=income,
        document_series=series,
        transfers=mock_transfers(income),
        warnings=warnings,
    )


def write_bundle(bundle: ReferenceBundle, bundles_dir: Path) -> Path:
    """Writes <bundles_dir>/<IČO>/<period>.json. Same exports, same bytes."""
    path = bundles_dir / bundle.entity.ico / f"{bundle.period}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(bundle.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def mock_transfers(income: Iterable[BudgetPosition]) -> list[Transfer]:
    """One transfer per grant row of the income side (EK 3xx, zdroj other than 41), because
    the software's Transfer list was not exported (plan section 3.2)."""
    return [
        Transfer(id=p.key, name=p.description or p.key, zdroj=p.zdroj)
        for p in income
        if p.ek.startswith("3") and p.zdroj != "41"
    ]


def _chart_entity(rows: list[list[object]]) -> tuple[Entity, str]:
    """Entity and period from the chart's two title rows:
    'UctovnyRozvrh, Obdobie: 08. 2026. IČO: 00305863' and 'Obec Boldog, Boldog 89, ...'."""
    title = _text(rows[0][0]) if rows else None
    match = _CHART_TITLE.search(title or "")
    if match is None or len(rows) < 2:
        raise IngestError(f"{CHART_FILE}: the title row has no period and IČO: {title!r}")
    month, year, ico = match.groups()
    name, _, address = (_text(rows[1][0]) or "").partition(",")
    entity = Entity(ico=ico.zfill(8), name=name.strip(), address=" ".join(address.split()) or None)
    return entity, f"{year}-{int(month):02d}"


def _accounts(rows: list[list[object]], warnings: list[IngestWarning]) -> list[Account]:
    _expect_header(rows, CHART_FILE, CHART_HEADER)
    accounts: dict[str, Account] = {}
    no_description = []
    for number, row in _data_rows(rows, CHART_FILE):
        try:
            su, au = _code(row[0], 3, "SU"), _code(row[1], 3, "AU")
            kind = ACCOUNT_TYPES.get(_text(row[2]) or "")
            if kind is None:
                raise _RowError(f"unknown account type {row[2]!r}")
        except _RowError as exc:
            warnings.append(_skipped(CHART_FILE, number, exc))
            continue
        key = f"{su} {au}"
        if key in accounts:
            warnings.append(
                IngestWarning(
                    code="duplicate_key",
                    source=CHART_FILE,
                    rows=[accounts[key].row, number],
                    message=f"account {key} appears again; the first row is kept",
                )
            )
            continue
        description = _text(row[6])
        if description is None:
            no_description.append(number)
        accounts[key] = Account(
            key=key,
            su=su,
            au=au,
            type=kind,
            activity=_text(row[5]),
            description=description,
            row=number,
        )
    _report_missing_descriptions(no_description, CHART_FILE, warnings)
    return list(accounts.values())


@dataclass
class _Group:
    parts: tuple[str, str, str | None, str | None, str]
    rows: list[int] = field(default_factory=list)
    descriptions: list[str | None] = field(default_factory=list)


def _budget_positions(
    rows: list[list[object]], source: str, warnings: list[IngestWarning], *, with_function: bool
) -> list[BudgetPosition]:
    """Expense rows carry the function code (oddiel, trieda); income rows do not."""
    _expect_header(rows, source, BUDGET_HEADER)
    groups: dict[str, _Group] = {}
    for number, row in _data_rows(rows, source):
        try:
            ek, zdroj = _code(row[0], 6, "Kód"), _zdroj(row[1])
            if with_function:
                oddiel, trieda = _code(row[2], 2, "Oddiel"), _code(row[3], 3, "Trieda")
            else:
                oddiel, trieda = (
                    _optional_code(row[2], 2, "Oddiel"),
                    _optional_code(row[3], 3, "Trieda"),
                )
            analytika = _code(row[4], 3, "Analytika")
        except _RowError as exc:
            warnings.append(_skipped(source, number, exc))
            continue
        key = budget_key(ek, zdroj, oddiel, trieda, analytika)
        group = groups.setdefault(key, _Group(parts=(ek, zdroj, oddiel, trieda, analytika)))
        group.rows.append(number)
        group.descriptions.append(_text(row[5]))

    positions = []
    no_description = []
    for key, group in groups.items():
        texts = list(dict.fromkeys(d for d in group.descriptions if d))
        no_description += [n for n, d in zip(group.rows, group.descriptions, strict=True) if not d]
        if len(group.rows) > 1:
            warnings.append(
                IngestWarning(
                    code="duplicate_key",
                    source=source,
                    rows=group.rows,
                    message=f"{key} appears {len(group.rows)} times; merged, keeping the "
                    f"descriptions {texts}",
                )
            )
        ek, zdroj, oddiel, trieda, analytika = group.parts
        positions.append(
            BudgetPosition(
                key=key,
                ek=ek,
                zdroj=zdroj,
                oddiel=oddiel,
                trieda=trieda,
                analytika=analytika,
                description=texts[0] if texts else None,
                aliases=texts[1:],
                rows=group.rows,
            )
        )
    _report_missing_descriptions(sorted(no_description), source, warnings)
    return positions


def _document_series(
    rows: list[list[object]], warnings: list[IngestWarning]
) -> list[DocumentSeries]:
    _expect_header(rows, SERIES_FILE, SERIES_HEADER)
    series = []
    for number, row in _data_rows(rows, SERIES_FILE):
        pattern = _text(row[1])
        if pattern is None:
            warnings.append(_skipped(SERIES_FILE, number, _RowError("no Vzor dokladu")))
            continue
        series.append(
            DocumentSeries(
                code=pattern.split("/")[0],
                series_id=_text(row[0]) or "",
                pattern=pattern,
                description=_text(row[2]) or "",
                bank_account=_text(row[3]),
            )
        )
    return series


def _data_rows(rows: list[list[object]], source: str) -> Iterable[tuple[int, list[object]]]:
    """(sheet row number, cells) of every non-empty data row."""
    for number, row in enumerate(rows[HEADER_ROWS[source] :], start=HEADER_ROWS[source] + 1):
        if any(_text(cell) for cell in row):
            yield number, row


def _expect_header(rows: list[list[object]], source: str, expected: list[str]) -> None:
    index = HEADER_ROWS[source] - 1
    found = [_text(cell) for cell in rows[index]] if len(rows) > index else []
    if found[: len(expected)] != expected:
        raise IngestError(f"{source}: expected the columns {expected}, found {found}")


def _report_missing_descriptions(
    rows: list[int], source: str, warnings: list[IngestWarning]
) -> None:
    if rows:
        warnings.append(
            IngestWarning(
                code="missing_description",
                source=source,
                rows=rows,
                message=f"{len(rows)} rows have no Popis",
            )
        )


def _skipped(source: str, number: int, error: Exception) -> IngestWarning:
    return IngestWarning(code="skipped_row", source=source, rows=[number], message=str(error))


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text or None


def _code(value: object, width: int, column: str) -> str:
    text = _text(value)
    if text is None or not _DIGITS.fullmatch(text) or len(text) > width:
        raise _RowError(f"{column} {value!r} is not a code of {width} digits")
    return text.zfill(width)


def _optional_code(value: object, width: int, column: str) -> str | None:
    return None if _text(value) is None else _code(value, width, column)


def _zdroj(value: object) -> str:
    text = _text(value)
    if text is None or not _ZDROJ.fullmatch(text):
        raise _RowError(f"Zdroj {value!r} is not a source code")
    return text
