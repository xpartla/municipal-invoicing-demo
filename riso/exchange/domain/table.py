"""A file read for import, whatever its format: a uniform table of rows and cells that keeps
each row's number in the source (plan §9.2 step 1).

Readers (`riso.exchange.infrastructure.readers`) turn a CSV, XLSX or XLS file into raw rows;
`Table.from_rows` splits them at the header row into the rows above it (the preamble, where
TOPSET puts the period and the IČO), the columns and the data rows. A cell holds what the file
holds: text, a whole number, a decimal, a date or a time, a boolean, or nothing.

The header row is guessed (`guess_header_row`) and can be chosen; 0 means the file has none,
and the columns are then named by their letters.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from riso.shared.errors import NotFound, ValidationFailed

CellValue = str | int | Decimal | date | datetime | bool | None
"""A cell. Excel's numbers arrive as `int` when whole and `Decimal` otherwise; CSV gives
text only. An empty cell is None."""

MAX_ROWS = 100_000
MAX_COLUMNS = 200
HEADER_SCAN = 30
"""How many rows from the top `guess_header_row` looks at."""

_NUMERIC = re.compile(r"[-+]?[\d\s.,]+")


class FileFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"
    XLS = "xls"


@dataclass(frozen=True, slots=True)
class ReadOptions:
    """How to read a file. None leaves the choice to the reader: the first sheet, the guessed
    header row, the detected encoding and delimiter."""

    sheet: str | None = None
    header_row: int | None = None
    """1-based; 0 for a file without a header row."""
    encoding: str | None = None
    """CSV only: `utf-8` or `windows-1250` (or another Python codec name)."""
    delimiter: str | None = None
    """CSV only: one character."""

    def __post_init__(self) -> None:
        if self.header_row is not None and not 0 <= self.header_row <= HEADER_SCAN:
            raise ValidationFailed.on(
                "header_row", f"between 0 and {HEADER_SCAN}", "header_row_range"
            )
        if self.delimiter is not None and len(self.delimiter) != 1:
            raise ValidationFailed.on("delimiter", "one character", "delimiter_length")


def column_letter(index: int) -> str:
    """The spreadsheet letter of a 0-based column index: 0 → A, 26 → AA."""
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def cell_text(value: CellValue) -> str | None:
    """A cell as text, as a person reads it: a whole number without `.0`, a date as ISO 8601,
    surrounding whitespace removed; None for an empty cell."""
    if value is None:
        return None
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, datetime):
        text = (
            value.date().isoformat() if value.time() == datetime.min.time() else value.isoformat()
        )
    elif isinstance(value, date):
        text = value.isoformat()
    elif isinstance(value, Decimal):
        text = format(value.normalize(), "f") if value == value.to_integral() else str(value)
    else:
        text = str(value)
    text = text.strip()
    return text or None


def _header_text(value: CellValue) -> str:
    return " ".join((cell_text(value) or "").split())


@dataclass(frozen=True, slots=True)
class Column:
    index: int
    """0-based."""
    header: str
    """The header cell's text with whitespace collapsed; empty without one."""
    key: str
    """How a mapping names the column: the header, or `#<letter>` when the header is empty or
    repeats an earlier one."""

    @property
    def letter(self) -> str:
        return column_letter(self.index)


@dataclass(frozen=True, slots=True)
class TableRow:
    number: int
    """The row's number in the sheet, or the record's in a CSV file (1-based)."""
    cells: tuple[CellValue, ...]

    def value(self, index: int) -> CellValue:
        return self.cells[index] if index < len(self.cells) else None

    @property
    def empty(self) -> bool:
        return all(cell_text(cell) is None for cell in self.cells)


@dataclass(frozen=True, slots=True)
class Table:
    columns: tuple[Column, ...]
    rows: tuple[TableRow, ...]
    """Every row below the header, empty ones included (a mapping skips those)."""
    header_row: int
    """1-based; 0 without a header row."""
    preamble: tuple[tuple[CellValue, ...], ...] = ()
    """The rows above the header row."""

    @classmethod
    def from_rows(
        cls, rows: Sequence[Sequence[CellValue]], header_row: int | None = None
    ) -> "Table":
        """Splits raw rows at the header row (guessed when None)."""
        if len(rows) > MAX_ROWS + HEADER_SCAN:
            raise ValidationFailed.on("file", f"more than {MAX_ROWS} rows", "too_many_rows")
        if header_row is None:
            header_row = guess_header_row(rows)
        if header_row > len(rows):
            raise ValidationFailed.on(
                "header_row", f"the file has only {len(rows)} rows", "header_row_range"
            )
        width = max((len(row) for row in rows), default=0)
        if width > MAX_COLUMNS:
            raise ValidationFailed.on(
                "file", f"more than {MAX_COLUMNS} columns", "too_many_columns"
            )
        header = list(rows[header_row - 1]) if header_row else []
        seen: set[str] = set()
        columns = []
        for index in range(width):
            text = _header_text(header[index]) if index < len(header) else ""
            key = text if text and text not in seen else f"#{column_letter(index)}"
            seen.add(text)
            columns.append(Column(index, text, key))
        data = [
            TableRow(number, tuple(row) + (None,) * (width - len(row)))
            for number, row in enumerate(rows[header_row:], start=header_row + 1)
        ]
        if len(data) > MAX_ROWS:
            raise ValidationFailed.on("file", f"more than {MAX_ROWS} rows", "too_many_rows")
        preamble = tuple(tuple(row) for row in rows[: max(header_row - 1, 0)])
        return cls(tuple(columns), tuple(data), header_row, preamble)

    def column(self, key: str) -> Column:
        for column in self.columns:
            if column.key == key:
                return column
        raise NotFound(f"no column {key!r}")

    def has_column(self, key: str) -> bool:
        return any(column.key == key for column in self.columns)

    @property
    def data_rows(self) -> int:
        """The rows below the header, empty ones included, as `riso ingest` counts them."""
        return len(self.rows)

    @property
    def headers(self) -> tuple[str, ...]:
        return tuple(column.header for column in self.columns)


def _is_label(value: CellValue) -> bool:
    text = cell_text(value)
    return isinstance(value, str) and text is not None and not _NUMERIC.fullmatch(text)


def guess_header_row(rows: Sequence[Sequence[CellValue]]) -> int:
    """The first of the top rows that looks like a header: at least two filled cells, every
    filled cell a label (text that is not a number), and nearly as wide as the widest row
    near it. 0 when no row does. TOPSET's chart of accounts has two title rows above its
    header; they have one filled cell each and are passed over."""
    top = rows[:HEADER_SCAN]
    filled = [[cell for cell in row if cell_text(cell) is not None] for row in top]
    widest = max((len(cells) for cells in filled), default=0)
    needed = max(2, -(-widest * 3 // 5))  # 60 %, rounded up
    for number, cells in enumerate(filled, start=1):
        if len(cells) >= needed and all(_is_label(cell) for cell in cells):
            return number
    return 0


@dataclass(frozen=True, slots=True)
class Workbook:
    """What a reader found in a file: its format, its sheets (one, unnamed, for CSV), the
    choices it made, and the chosen sheet's rows as a table."""

    format: FileFormat
    sheets: tuple[str, ...]
    sheet: str | None
    """The sheet read; None for CSV."""
    table: Table
    encoding: str | None = None
    """CSV only."""
    delimiter: str | None = None
    """CSV only."""

    @property
    def options(self) -> ReadOptions:
        """The options that read the file this way again."""
        return ReadOptions(
            sheet=self.sheet,
            header_row=self.table.header_row,
            encoding=self.encoding,
            delimiter=self.delimiter,
        )
