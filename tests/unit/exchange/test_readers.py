"""Reading CSV, XLSX and XLS files (P2-M3-T01). Every fixture is generated here; no real
export is committed. With the raw exports present, the four TOPSET files read with the row
counts `riso ingest` sees."""

import codecs
import contextlib
import csv
import io
import zipfile
from datetime import date, datetime
from decimal import Decimal

import openpyxl
import pytest
import xlwt
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from riso.exchange.domain.table import FileFormat, ReadOptions
from riso.exchange.infrastructure.readers import (
    DELIMITERS,
    MAX_FILE_BYTES,
    detect_delimiter,
    detect_encoding,
    detect_format,
    read_workbook,
)
from riso.ingest.build import CHART_FILE, EXPENSE_FILE, HEADER_ROWS, INCOME_FILE, SERIES_FILE
from riso.ingest.excel import read_rows
from riso.shared import ValidationFailed

ROWS = [
    ["Kód", "Zdroj", "Popis"],
    ["632001", "41", "Energie – elektrina"],
    ["637004", "41", "Všeobecné služby; čistenie"],
    ["637005", "111", 'Špeciálne služby "audit"'],
]


def _csv(rows, delimiter=";", encoding="utf-8", newline="\r\n") -> bytes:
    out = io.StringIO()
    csv.writer(out, delimiter=delimiter, lineterminator=newline).writerows(rows)
    return out.getvalue().encode(encoding)


def _code(caught) -> str:
    return caught.value.errors[0].code


def _xlsx(sheets: dict[str, list[list[object]]]) -> bytes:
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def _xls(sheets: dict[str, list[list[object]]]) -> bytes:
    workbook = xlwt.Workbook(encoding="utf-8")
    dates = xlwt.easyxf(num_format_str="DD.MM.YYYY")
    for name, rows in sheets.items():
        sheet = workbook.add_sheet(name)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                if value is None:
                    continue
                if isinstance(value, date):
                    sheet.write(r, c, value, dates)
                else:
                    sheet.write(r, c, value)
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


# CSV -------------------------------------------------------------------------------------


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "windows-1250", "utf-16"])
def test_csv_in_each_encoding(encoding):
    book = read_workbook(_csv(ROWS, encoding=encoding))
    assert book.format is FileFormat.CSV and book.sheets == () and book.sheet is None
    assert book.delimiter == ";"
    expected = {"utf-8": "utf-8", "utf-8-sig": "utf-8-sig", "windows-1250": "windows-1250"}
    assert book.encoding == expected.get(encoding, "utf-16")
    table = book.table
    assert table.header_row == 1 and table.headers == ("Kód", "Zdroj", "Popis")
    assert [list(r.cells) for r in table.rows] == ROWS[1:]
    assert [r.number for r in table.rows] == [2, 3, 4]


@pytest.mark.parametrize("delimiter", DELIMITERS)
def test_each_delimiter_is_detected(delimiter):
    book = read_workbook(_csv(ROWS, delimiter=delimiter))
    assert book.delimiter == delimiter
    assert book.table.rows[1].cells[2] == "Všeobecné služby; čistenie"


def test_decimal_commas_do_not_fool_the_delimiter():
    data = "Kód;Suma;Popis\n632001;1,50;Energie\n637004;12,00;Služby\n".encode()
    assert read_workbook(data).delimiter == ";"


def test_a_single_column_file_reads_as_one_column():
    assert detect_delimiter("Popis\nEnergie\nSlužby\n") == ","
    data = "Popis\nEnergie\nSlužby\n".encode()
    # One label is too little to guess a header from; the wizard lets the user choose it.
    assert read_workbook(data).table.header_row == 0
    book = read_workbook(data, ReadOptions(header_row=1))
    assert [r.cells for r in book.table.rows] == [("Energie",), ("Služby",)]


def test_newlines_inside_quoted_fields_keep_the_record_numbers():
    data = _csv([["Kód", "Popis"], ["1", "riadok\ndruhý"], ["2", "ďalší"]])
    table = read_workbook(data).table
    assert [r.number for r in table.rows] == [2, 3]
    assert table.rows[0].cells[1] == "riadok\ndruhý"


def test_empty_cells_are_none_and_spaces_are_kept():
    table = read_workbook(b"a;b;c\n1;;  x \n").table
    assert table.rows[0].cells == ("1", None, "  x ")


def test_the_encoding_and_delimiter_can_be_overridden():
    data = _csv(ROWS, delimiter=",", encoding="windows-1250")
    book = read_workbook(data, ReadOptions(header_row=1, encoding="windows-1250", delimiter=";"))
    assert book.delimiter == ";" and book.table.columns[0].header == "Kód,Zdroj,Popis"
    with pytest.raises(ValidationFailed) as caught:
        read_workbook(data, ReadOptions(encoding="utf-8"))
    assert _code(caught) == "wrong_encoding"
    with pytest.raises(ValidationFailed) as caught:
        read_workbook(data, ReadOptions(encoding="klingon"))
    assert _code(caught) == "unknown_encoding"


def test_a_file_valid_in_neither_encoding_goes_to_charset_normalizer():
    # 0x81 is undefined in Windows-1250 and not UTF-8; ISO-8859-2 reads it.
    data = "kód;názov\n1;Žltá škola\n".encode("iso-8859-2") + b"\x81\n"
    with pytest.raises(UnicodeDecodeError):
        data.decode("windows-1250")
    assert detect_encoding(data) not in ("utf-8", "windows-1250")
    read_workbook(data)  # reads, whatever the guess


def test_utf8_wins_bytes_valid_in_both():
    data = "Čž".encode("windows-1250")  # C8 9E: also valid UTF-8
    assert data.decode("utf-8") and detect_encoding(data) == "utf-8"


def test_a_sheet_is_refused_for_csv():
    with pytest.raises(ValidationFailed) as caught:
        read_workbook(_csv(ROWS), ReadOptions(sheet="Hárok1"))
    assert _code(caught) == "no_sheets"


slovak = st.text(
    alphabet=st.sampled_from(
        "abcdeghijklmnoprstuvyzABCDEGHIJKLMNOPRSTUVYZ0123456789 .-/\"'\n"
        "áäčďéíĺľňóôŕšťúýžÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ"
    ),
    max_size=12,
)


@settings(max_examples=150, suppress_health_check=[HealthCheck.filter_too_much])
@given(
    rows=st.integers(min_value=2, max_value=6).flatmap(
        lambda width: st.lists(st.lists(slovak, min_size=width, max_size=width), min_size=1)
    ),
    delimiter=st.sampled_from(DELIMITERS),
    encoding=st.sampled_from(["utf-8", "utf-8-sig", "windows-1250"]),
    newline=st.sampled_from(["\r\n", "\n"]),
)
def test_csv_round_trips_with_any_delimiter_and_encoding(rows, delimiter, encoding, newline):
    assume(any(cell.strip() for row in rows for cell in row))  # an empty file has no delimiter
    data = _csv(rows, delimiter, encoding, newline)
    if encoding == "windows-1250":
        # Bytes that also read as UTF-8 are ambiguous; UTF-8 wins them (see the module).
        with contextlib.suppress(UnicodeDecodeError):
            assume(data.decode("utf-8") == data.decode("windows-1250"))
    book = read_workbook(data, ReadOptions(header_row=0))
    assert book.delimiter == delimiter
    assert codecs.lookup(book.encoding).name == codecs.lookup(encoding).name or data.isascii()
    expected = [[cell or None for cell in row] for row in rows]
    assert [list(r.cells) for r in book.table.rows] == expected
    assert [r.number for r in book.table.rows] == list(range(1, len(rows) + 1))


# Excel -----------------------------------------------------------------------------------

SHEET = [
    ["Kód", "Zdroj", "Suma", "Dátum", "Popis"],
    [632001, 41, 1.5, date(2026, 6, 11), "Energie"],
    [637004, "72f", 12, None, "Služby"],
]


def test_xlsx_with_typed_cells_and_sheets():
    data = _xlsx({"Výdavky": SHEET, "Príjmy": [["Kód", "Popis"], [312001, "Dane"]]})
    book = read_workbook(data)
    assert book.format is FileFormat.XLSX
    assert book.sheets == ("Výdavky", "Príjmy") and book.sheet == "Výdavky"
    first, second = book.table.rows
    assert first.cells == (632001, 41, Decimal("1.5"), datetime(2026, 6, 11), "Energie")
    assert second.cells == (637004, "72f", 12, None, "Služby")
    other = read_workbook(data, ReadOptions(sheet="Príjmy"))
    assert other.sheet == "Príjmy" and other.table.rows[0].cells == (312001, "Dane")
    assert other.options == ReadOptions(sheet="Príjmy", header_row=1)


def test_xls_with_typed_cells_and_sheets():
    data = _xls({"Hárok1": SHEET, "Druhý": [["Kód", "Popis"], [312001, "Dane"]]})
    book = read_workbook(data)
    assert book.format is FileFormat.XLS and book.sheets == ("Hárok1", "Druhý")
    first, second = book.table.rows
    assert first.cells == (632001, 41, Decimal("1.5"), datetime(2026, 6, 11), "Energie")
    assert second.cells == (637004, "72f", 12, None, "Služby")
    assert read_workbook(data, ReadOptions(sheet="Druhý")).table.rows[0].cells == (312001, "Dane")


@pytest.mark.parametrize("make", [_xlsx, _xls])
def test_an_unknown_sheet_is_refused(make):
    with pytest.raises(ValidationFailed) as caught:
        read_workbook(make({"Hárok1": SHEET}), ReadOptions(sheet="Iný"))
    assert _code(caught) == "unknown_sheet"


@pytest.mark.parametrize("make", [_xlsx, _xls])
def test_the_header_row_can_be_chosen_in_a_workbook(make):
    rows = [["Výkaz výdavkov 2026"], *SHEET]
    assert read_workbook(make({"S": rows})).table.header_row == 2
    table = read_workbook(make({"S": rows}), ReadOptions(header_row=0)).table
    assert table.rows[0].cells[0] == "Výkaz výdavkov 2026"


# Recognising the format by content ---------------------------------------------------------


def test_the_format_comes_from_the_content_not_the_name():
    assert detect_format(_xlsx({"S": SHEET})) is FileFormat.XLSX
    assert detect_format(_xls({"S": SHEET})) is FileFormat.XLS
    assert detect_format(_csv(ROWS)) is FileFormat.CSV


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"", "empty_file"),
        (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "unsupported_format"),
        (b"PK\x03\x04garbage", "damaged_file"),
        (bytes.fromhex("d0cf11e0a1b11ae1") + b"\x00" * 100, "damaged_file"),
    ],
)
def test_unreadable_files_are_refused(data, code):
    with pytest.raises(ValidationFailed) as caught:
        read_workbook(data)
    assert _code(caught) == code


def test_a_zip_that_is_not_a_workbook_is_refused():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("content.xml", "<x/>")  # e.g. an OpenDocument file
    with pytest.raises(ValidationFailed) as caught:
        read_workbook(out.getvalue())
    assert _code(caught) == "unsupported_format"


def test_size_limits():
    with pytest.raises(ValidationFailed) as caught:
        read_workbook(b"a" * (MAX_FILE_BYTES + 1))
    assert _code(caught) == "file_too_large"
    with pytest.raises(ValidationFailed) as caught:
        read_workbook(b"a;b\n" * 100_100)
    assert _code(caught) == "too_many_rows"


# The real TOPSET exports, when present ------------------------------------------------------


def test_the_four_topset_exports_read_like_riso_ingest_reads_them(raw_dir):
    expected = {CHART_FILE: 435, EXPENSE_FILE: 458, INCOME_FILE: 122, SERIES_FILE: 13}
    for name, data_rows in expected.items():
        book = read_workbook((raw_dir / name).read_bytes())
        table = book.table
        assert table.header_row == HEADER_ROWS[name], name
        assert table.data_rows == len(read_rows(raw_dir / name)) - HEADER_ROWS[name], name
        assert sum(not row.empty for row in table.rows) == data_rows, name
    chart = read_workbook((raw_dir / CHART_FILE).read_bytes())
    assert chart.format is FileFormat.XLS
    assert chart.table.headers[:2] == ("SU", "AU")
    assert "IČO" in chart.table.preamble[0][0]
