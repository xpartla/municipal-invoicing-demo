import pytest

from riso.reference import ParsedNumber, format_number, parse_number


def test_the_handwritten_number_fills_the_series_pattern():
    assert format_number("FD/XXX/RR", 144, 2026) == "FD/144/26"
    assert format_number("FDŠJ/XXX/RR", 7, 2026) == "FDŠJ/007/26"
    assert format_number("BU1/MM-RR/XXX", 5, 2026, month=7) == "BU1/07-26/005"


def test_a_pattern_with_a_month_needs_one():
    with pytest.raises(ValueError, match="needs a month"):
        format_number("BU1/MM-RR/XXX", 5, 2026)


def test_numbers_parse_back_into_their_parts():
    assert parse_number("FD/XXX/RR", "FD/144/26") == ParsedNumber(144, 26, None)
    assert parse_number("FD/XXX/RR", "FD/1001/26") == ParsedNumber(1001, 26, None)
    assert parse_number("BU1/MM-RR/XXX", "BU1/07-26/005") == ParsedNumber(5, 26, 7)


@pytest.mark.parametrize("number", ["FDŠJ/144/26", "FD/14/26", "FD/144/2026", "FD/144"])
def test_numbers_outside_the_pattern_do_not_parse(number):
    assert parse_number("FD/XXX/RR", number) is None
