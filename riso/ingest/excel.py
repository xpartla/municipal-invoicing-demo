"""Reading the exports: .xlsx through openpyxl, the old binary .xls through xlrd."""

from pathlib import Path

import openpyxl
import xlrd


def read_rows(path: Path) -> list[list[object]]:
    """Every row of the first sheet; sheet row n is item n - 1."""
    if path.suffix.lower() == ".xls":
        sheet = xlrd.open_workbook(str(path)).sheet_by_index(0)
        return [sheet.row_values(r) for r in range(sheet.nrows)]
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return [list(row) for row in workbook.worksheets[0].iter_rows(values_only=True)]
    finally:
        workbook.close()
