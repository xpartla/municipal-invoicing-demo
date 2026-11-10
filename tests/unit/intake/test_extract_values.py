"""The value readers of the field extractor (P2-M5-T05)."""

import datetime as dt
from decimal import Decimal

import pytest

from riso.intake.domain.extract import values


@pytest.mark.parametrize(
    ("text", "amount"),
    [
        ("Celkom k úhrade: 1 234,56 €", "1234.56"),
        ("1.234,56 EUR", "1234.56"),
        ("93,71", "93.71"),
        ("-52,27 €", "-52.27"),
        ("Spolu 1 593,12", "1593.12"),
        ("Total 1234.56", "1234.56"),
    ],
)
def test_amounts_as_printed(text, amount):
    assert values.amounts(text)[-1][0] == Decimal(amount)


def test_unit_prices_with_four_decimals_are_not_amounts():
    assert values.amounts("0,1389") == []


@pytest.mark.parametrize(
    ("text", "day"),
    [
        ("Dátum vystavenia: 1.7.2026", dt.date(2026, 7, 1)),
        ("01.07.2026", dt.date(2026, 7, 1)),
        ("1. 7. 2026", dt.date(2026, 7, 1)),
        ("23.6.26", dt.date(2026, 6, 23)),
    ],
)
def test_dates_as_printed(text, day):
    assert values.dates(text)[0][0] == day


def test_impossible_dates_are_skipped():
    assert values.dates("31.2.2026") == [] and values.dates("1.13.2026") == []


@pytest.mark.parametrize(
    ("text", "ico"),
    [
        ("IČO: 35823551", "35823551"),
        ("IČO 35 823 551", "35823551"),
        ("IČO: 3582355l", "35823551"),
        ("IČO: 305863", "00305863"),
    ],
)
def test_icos_with_spaces_confusions_and_old_lengths(text, ico):
    assert values.icos(text)[0][0] == ico


def test_ibans_grouped_or_compact_and_checked():
    [((iban, valid), _)] = values.ibans("IBAN: SK80 1100 0000 0026 2410 5532")
    assert iban == "SK8011000000002624105532" and valid
    [((_, valid), _)] = values.ibans("SK8111000000002624105532")
    assert not valid


def test_dic_and_ic_dph():
    assert values.dics("DIČ: 2020285512")[0][0] == "2020285512"
    assert values.ic_dphs("IČ DPH: SK 2020285512")[0][0] == "SK2020285512"


def test_document_numbers_need_a_digit():
    assert [v for v, _ in values.document_numbers("č. 2026/0012")] == ["2026/0012"]
    assert values.document_numbers("č. FAKTURA") == []
