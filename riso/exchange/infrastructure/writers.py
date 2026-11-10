"""The export files (plan §7.4): CSV for Slovak Excel (UTF-8 with a BOM, `;` between cells,
decimal comma, `dd.mm.yyyy` dates, CRLF line ends) and XLSX (typed numbers and dates). Text
cells go through the formula guard; amounts are rounded half up to cents."""

import csv
import io
from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from riso.exchange.domain.export import Cell, Column, ExportFormat, guard

CENT = Decimal("0.01")


def _amount(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _csv_cell(cell: Cell) -> str:
    if cell is None:
        return ""
    if isinstance(cell, Decimal):
        return format(_amount(cell), "f").replace(".", ",")
    if isinstance(cell, date):
        return cell.strftime("%d.%m.%Y")
    return guard(cell)


def csv_bytes(columns: Sequence[Column], rows: Sequence[Sequence[Cell]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow([column.header for column in columns])
    for row in rows:
        writer.writerow([_csv_cell(cell) for cell in row])
    return ("﻿" + out.getvalue()).encode("utf-8")


def xlsx_bytes(columns: Sequence[Column], rows: Sequence[Sequence[Cell]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Faktúry"
    sheet.append([column.header for column in columns])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    for row in rows:
        values: list[object] = []
        for value in row:
            if isinstance(value, Decimal):
                values.append(_amount(value))
            elif isinstance(value, str):
                values.append(guard(value))
            else:
                values.append(value)
        sheet.append(values)
    for index, column in enumerate(columns, start=1):
        letter = get_column_letter(index)
        sheet.column_dimensions[letter].width = max(10, len(column.header) + 2)
        if column.kind == "text":
            continue
        style = "0.00" if column.kind == "number" else "dd.mm.yyyy"
        for (cell,) in sheet.iter_rows(min_row=2, min_col=index, max_col=index):
            cell.number_format = style
    for row_cells in sheet.iter_rows(min_row=2):
        for cell in row_cells:
            if isinstance(cell.value, str):
                cell.data_type = "s"  # never a formula, whatever the text starts with
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


class TableWriter:
    """The exchange context's `ExportWriter`."""

    def write(
        self,
        export_format: ExportFormat,
        columns: Sequence[Column],
        rows: Sequence[Sequence[Cell]],
    ) -> bytes:
        if export_format is ExportFormat.CSV:
            return csv_bytes(columns, rows)
        return xlsx_bytes(columns, rows)
