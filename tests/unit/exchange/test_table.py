"""The uniform table a read file becomes (P2-M3-T01): header detection, column keys, row
numbers, the preamble and the text of a cell."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from riso.exchange.domain.table import (
    MAX_COLUMNS,
    ReadOptions,
    Table,
    cell_text,
    column_letter,
    guess_header_row,
)
from riso.shared import NotFound, ValidationFailed

TOPSET_CHART = [
    ["UctovnyRozvrh, Obdobie: 08. 2026. IČO: 00305863", None, None],
    ["Obec Boldog, Boldog 89, 925 28 Boldog", None, None],
    ["SU", "AU", "Popis"],
    [518, 1, "Telefóny"],
    [None, None, None],
    [518, 3, "Internet"],
]


def test_column_letters():
    assert [column_letter(i) for i in (0, 1, 25, 26, 27, 51, 52, 701, 702)] == [
        "A",
        "B",
        "Z",
        "AA",
        "AB",
        "AZ",
        "BA",
        "ZZ",
        "AAA",
    ]


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (None, None),
        ("  ", None),
        ("  Popis ", "Popis"),
        (41, "41"),
        (Decimal("41"), "41"),
        (Decimal("41.50"), "41.50"),
        (Decimal("1E+2"), "100"),
        (True, "true"),
        (date(2026, 6, 11), "2026-06-11"),
        (datetime(2026, 6, 11), "2026-06-11"),
        (datetime(2026, 6, 11, 8, 30), "2026-06-11T08:30:00"),
    ],
)
def test_cell_text(value, text):
    assert cell_text(value) == text


def test_the_header_is_found_below_topsets_two_title_rows():
    assert guess_header_row(TOPSET_CHART) == 3
    table = Table.from_rows(TOPSET_CHART)
    assert table.header_row == 3
    assert table.headers == ("SU", "AU", "Popis")
    assert [len(row) for row in table.preamble] == [3, 3]
    assert table.preamble[0][0].startswith("UctovnyRozvrh")
    # Row numbers are the sheet's; the empty row stays, as riso ingest counts it.
    assert [row.number for row in table.rows] == [4, 5, 6]
    assert table.data_rows == 3
    assert table.rows[1].empty and not table.rows[0].empty


def test_a_header_on_the_first_row():
    rows = [["code", "name"], ["632", "Energie"], ["633", "Materiál"]]
    assert guess_header_row(rows) == 1
    table = Table.from_rows(rows)
    assert [r.number for r in table.rows] == [2, 3]


@pytest.mark.parametrize(
    "rows",
    [
        [["632", "Energie"], ["633", "Materiál"]],  # the first row has a number
        [["Jediný stĺpec"], ["a"], ["b"]],  # one filled cell is not a header
        [],
    ],
)
def test_no_header_is_guessed_when_no_row_looks_like_one(rows):
    assert guess_header_row(rows) == 0


def test_numbers_written_as_text_are_not_labels():
    assert guess_header_row([["1 234,50", "12.6.2026"], ["Kód", "Popis"], ["1", "a"]]) == 2


def test_without_a_header_the_columns_are_named_by_their_letters():
    table = Table.from_rows([["632", "Energie"], ["633"]], header_row=0)
    assert [c.key for c in table.columns] == ["#A", "#B"]
    assert [c.header for c in table.columns] == ["", ""]
    assert table.rows[1].cells == ("633", None)  # short rows are padded
    assert [r.number for r in table.rows] == [1, 2]


def test_empty_and_repeated_headers_get_letter_keys():
    table = Table.from_rows([["Popis", None, "Popis", " Zdroj  účtu "], ["a", "b", "c", "d"]], 1)
    assert [c.key for c in table.columns] == ["Popis", "#B", "#C", "Zdroj účtu"]
    assert table.column("#C").header == "Popis"
    assert table.column("Zdroj účtu").letter == "D"
    assert table.has_column("Popis") and not table.has_column("Kód")
    with pytest.raises(NotFound):
        table.column("Kód")


def test_a_chosen_header_row_overrides_the_guess():
    table = Table.from_rows(TOPSET_CHART, header_row=1)
    assert table.header_row == 1 and table.preamble == ()
    assert table.columns[0].header.startswith("UctovnyRozvrh")
    assert table.data_rows == 5


def test_a_header_row_past_the_end_is_refused():
    with pytest.raises(ValidationFailed) as caught:
        Table.from_rows([["a", "b"]], header_row=3)
    assert caught.value.errors[0].code == "header_row_range"


def test_too_many_columns_are_refused():
    with pytest.raises(ValidationFailed) as caught:
        Table.from_rows([["x"] * (MAX_COLUMNS + 1)], header_row=0)
    assert caught.value.errors[0].code == "too_many_columns"


@pytest.mark.parametrize(
    ("options", "code"),
    [
        ({"header_row": -1}, "header_row_range"),
        ({"header_row": 31}, "header_row_range"),
        ({"delimiter": ";;"}, "delimiter_length"),
    ],
)
def test_read_options_are_checked(options, code):
    with pytest.raises(ValidationFailed) as caught:
        ReadOptions(**options)
    assert caught.value.errors[0].code == code
