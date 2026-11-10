import datetime as dt
from decimal import Decimal

import pytest

from riso.testdata import printed
from riso.testdata.printed import NBSP


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("1234.5", f"1{NBSP}234,50"),
        ("93.71", "93,71"),
        ("-52.27", "-52,27"),
        ("0.1389", "0,1389"),
        ("1234567.891234", f"1{NBSP}234{NBSP}567,8912"),
        ("700", "700,00"),
    ],
)
def test_amounts_have_a_decimal_comma_and_grouped_thousands(value, text):
    assert printed.amount(Decimal(value)) == text


def test_quantities_drop_trailing_zeros():
    assert printed.quantity(Decimal("1240")) == "1240"
    assert printed.quantity(Decimal("35.60")) == "35,6"


@pytest.mark.parametrize(
    ("style", "text"),
    [("dd.mm.yyyy", "01.07.2026"), ("d.m.yyyy", "1.7.2026"), ("d. m. yyyy", "1. 7. 2026")],
)
def test_dates_in_each_style(style, text):
    assert printed.date(dt.date(2026, 7, 1), style) == text


def test_ibans_grouped_or_compact_and_icos_spaced():
    assert printed.iban("sk80 1100000000262410 5532", grouped=True) == (
        "SK80 1100 0000 0026 2410 5532"
    )
    assert printed.iban("SK80 1100 0000 0026 2410 5532", grouped=False) == (
        "SK8011000000002624105532"
    )
    assert printed.ico("35823551", spaced=True) == "35 823 551"
    assert printed.ico("35823551", spaced=False) == "35823551"
