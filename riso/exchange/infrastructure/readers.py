"""Reading import files (plan §9.2 step 1): CSV, XLSX and XLS into a `Workbook`.

The format is recognised by content, never by the file name (plan §12): an XLSX file is a ZIP
holding `xl/workbook.xml`, an XLS file an OLE2 compound document, and anything else must be
text, read as CSV.

CSV encoding. A byte-order mark decides first (UTF-8, UTF-16). Otherwise a file that is valid
UTF-8 is UTF-8, and one that is not is Windows-1250, the code page TOPSET and Slovak Excel
write. Real Slovak text in Windows-1250 is practically never valid UTF-8 (an `á` followed by
an ASCII letter already is not), so the order is safe; only bytes valid in both remain
ambiguous, and UTF-8 wins those. A file valid in neither (Windows-1250 leaves five bytes
undefined) goes to charset-normalizer. The wizard can override the choice.

CSV delimiter. Each of `;`, `,`, tab and `|` is tried on the first records; a delimiter that
splits every non-empty record into the same number (more than one) of fields fits, and the
widest fit wins (the order above breaks ties). Without a fit (title rows above the header
have one field), the delimiter splitting the most records into the same number of fields
wins. The wizard can override it too.

XLSX is read by openpyxl (read-only, cached values, through defusedxml), XLS by xlrd. A whole
number arrives as `int`, any other number as `Decimal` (from the float's shortest repr), a
date cell as `datetime`. Limits: 20 MB per file, 200 MB unpacked for an XLSX file, 100,000
rows, 200 columns.
"""

import codecs
import csv
import io
import zipfile
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime, time
from decimal import Decimal
from typing import Literal

import charset_normalizer
import openpyxl
import xlrd

from riso.exchange.domain.table import (
    HEADER_SCAN,
    MAX_COLUMNS,
    MAX_ROWS,
    CellValue,
    FileFormat,
    ReadOptions,
    Table,
    Workbook,
)
from riso.shared.errors import ValidationFailed

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
DELIMITERS = (";", ",", "\t", "|")
SNIFF_RECORDS = 50
UTF8, WINDOWS_1250 = "utf-8", "windows-1250"

_OLE2 = bytes.fromhex("d0cf11e0a1b11ae1")
_ZIP = b"PK\x03\x04"
_MAX_RAW = MAX_ROWS + HEADER_SCAN


def _refuse(message: str, code: str, field: str = "file") -> ValidationFailed:
    return ValidationFailed.on(field, message, code)


def detect_format(data: bytes) -> FileFormat:
    if data.startswith(_OLE2):
        return FileFormat.XLS
    if data.startswith(_ZIP):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            raise _refuse("a damaged ZIP file", "damaged_file") from None
        if "xl/workbook.xml" in names:
            return FileFormat.XLSX
        raise _refuse("a ZIP file that is not an XLSX workbook", "unsupported_format")
    return FileFormat.CSV


def read_workbook(data: bytes, options: ReadOptions | None = None) -> Workbook:
    """The file's chosen sheet as a table. Raises `ValidationFailed` for a file it cannot
    read, naming why (`unsupported_format`, `too_many_rows`, …) in the field error's code."""
    options = options or ReadOptions()
    if not data:
        raise _refuse("the file is empty", "empty_file")
    if len(data) > MAX_FILE_BYTES:
        raise _refuse(f"larger than {MAX_FILE_BYTES // (1024 * 1024)} MB", "file_too_large")
    match detect_format(data):
        case FileFormat.XLSX:
            return _xlsx(data, options)
        case FileFormat.XLS:
            return _xls(data, options)
        case FileFormat.CSV:
            return _csv(data, options)


# CSV -------------------------------------------------------------------------------------


def detect_encoding(data: bytes) -> str:
    if data.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"
    for encoding in (UTF8, WINDOWS_1250):
        try:
            data.decode(encoding)
        except UnicodeDecodeError:
            continue
        return encoding
    best = charset_normalizer.from_bytes(data).best()
    if best is None:
        raise _refuse("the text encoding is not recognised", "unknown_encoding", "encoding")
    return best.encoding


def _decode(data: bytes, encoding: str) -> str:
    try:
        codecs.lookup(encoding)
    except LookupError:
        raise _refuse(f"unknown encoding {encoding!r}", "unknown_encoding", "encoding") from None
    try:
        text = data.decode(encoding)
    except UnicodeDecodeError:
        raise _refuse(f"the file is not {encoding}", "wrong_encoding", "encoding") from None
    text = text.removeprefix("﻿")
    if "\x00" in text:
        raise _refuse("not a text file", "unsupported_format")
    return text


def _records(text: str, delimiter: str, limit: int | None = None) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=False)
    records = []
    for record in reader:
        records.append(record)
        if limit is not None and len(records) >= limit:
            break
        if len(records) > _MAX_RAW:
            raise _refuse(f"more than {MAX_ROWS} rows", "too_many_rows")
    return records


def detect_delimiter(text: str) -> str:
    fits: list[tuple[int, int, str]] = []
    alike: list[tuple[int, int, str]] = []
    for rank, delimiter in enumerate(DELIMITERS):
        widths = [
            len(record)
            for record in _records(text, delimiter, SNIFF_RECORDS)
            if any(cell.strip() for cell in record)
        ]
        split = [width for width in widths if width > 1]
        if not split:
            continue
        common, count = Counter(split).most_common(1)[0]
        if count == len(widths):
            fits.append((common, -rank, delimiter))
        else:
            alike.append((count, -rank, delimiter))
    if fits:
        return max(fits)[2]
    if alike:
        return max(alike)[2]
    return ","


def _csv(data: bytes, options: ReadOptions) -> Workbook:
    if options.sheet is not None:
        raise _refuse("a CSV file has no sheets", "no_sheets", "sheet")
    encoding = options.encoding or detect_encoding(data)
    text = _decode(data, encoding)
    delimiter = options.delimiter or detect_delimiter(text)
    rows: list[list[CellValue]] = [
        [cell if cell != "" else None for cell in record] for record in _records(text, delimiter)
    ]
    table = Table.from_rows(rows, options.header_row)
    return Workbook(FileFormat.CSV, (), None, table, encoding=encoding, delimiter=delimiter)


# Excel -----------------------------------------------------------------------------------


def _number(value: float | int) -> int | Decimal:
    if isinstance(value, int):
        return value
    if value.is_integer():
        return int(value)
    return Decimal(repr(value))


def _excel_value(value: object) -> CellValue:
    if value is None or isinstance(value, bool | str | datetime):
        return value if value != "" else None
    if isinstance(value, int | float):
        return _number(value)
    if isinstance(value, time):
        return value.isoformat()
    return str(value)


def _choose(sheets: Sequence[str], wanted: str | None) -> str:
    if not sheets:
        raise _refuse("the workbook has no sheets", "no_sheets", "sheet")
    if wanted is None:
        return sheets[0]
    if wanted not in sheets:
        raise _refuse(f"no sheet {wanted!r}", "unknown_sheet", "sheet")
    return wanted


def _bounded(rows: Iterable[Sequence[CellValue]]) -> list[list[CellValue]]:
    """The rows without their trailing empty cells (a sheet's stated dimension often runs
    past its data), refusing more rows than the limit."""
    found: list[list[CellValue]] = []
    for row in rows:
        if len(found) >= _MAX_RAW:
            raise _refuse(f"more than {MAX_ROWS} rows", "too_many_rows")
        cells = list(row[: MAX_COLUMNS + 1])
        while cells and cells[-1] is None:
            cells.pop()
        found.append(cells)
    return found


def _check_unpacked(data: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(info.file_size for info in archive.infolist()) > MAX_UNPACKED_BYTES:
            raise _refuse("the workbook unpacks to too much data", "file_too_large")


def _xlsx(data: bytes, options: ReadOptions) -> Workbook:
    _check_unpacked(data)
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many kinds for a damaged file
        raise _refuse(f"the workbook does not open ({type(exc).__name__})", "damaged_file") from exc
    try:
        sheets = tuple(workbook.sheetnames)
        name = _choose(sheets, options.sheet)
        sheet = workbook[name]
        rows = _bounded(
            [_excel_value(value) for value in row[: MAX_COLUMNS + 1]]
            for row in sheet.iter_rows(values_only=True)
        )
    finally:
        workbook.close()
    return Workbook(FileFormat.XLSX, sheets, name, Table.from_rows(rows, options.header_row))


def _xls_value(cell: xlrd.sheet.Cell, datemode: Literal[0, 1]) -> CellValue:
    value = cell.value
    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
        return None
    if isinstance(value, float) and cell.ctype == xlrd.XL_CELL_DATE:
        try:
            return xlrd.xldate.xldate_as_datetime(value, datemode)
        except xlrd.xldate.XLDateError:
            return _number(value)
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(value)
    if isinstance(value, float):
        return _number(value)
    return _excel_value(value)


def _xls(data: bytes, options: ReadOptions) -> Workbook:
    try:
        workbook = xlrd.open_workbook(file_contents=data, on_demand=True)
    except Exception as exc:  # xlrd raises XLRDError, struct errors, … for a damaged file
        raise _refuse(f"the workbook does not open ({type(exc).__name__})", "damaged_file") from exc
    try:
        sheets = tuple(workbook.sheet_names())
        name = _choose(sheets, options.sheet)
        sheet = workbook.sheet_by_name(name)
        datemode: Literal[0, 1] = 1 if workbook.datemode == 1 else 0
        if sheet.nrows > _MAX_RAW:
            raise _refuse(f"more than {MAX_ROWS} rows", "too_many_rows")
        width = min(sheet.ncols, MAX_COLUMNS + 1)
        rows = _bounded(
            [_xls_value(sheet.cell(r, c), datemode) for c in range(width)]
            for r in range(sheet.nrows)
        )
    finally:
        workbook.release_resources()
    return Workbook(FileFormat.XLS, sheets, name, Table.from_rows(rows, options.header_row))


class FileTableReader:
    """The `TableReader` port on the readers above."""

    def read(self, data: bytes, options: ReadOptions | None = None) -> Workbook:
        return read_workbook(data, options)
