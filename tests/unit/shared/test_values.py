from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from riso.shared import Iban, Ico, Money, ValidationFailed, iban_is_valid, ico_is_valid

# --- IČO ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ico",
    [
        "00305863",  # Obec Boldog
        "35763469",
        "00000001",  # weighted sum 0: remainder 0 gives check digit 1
        "00000060",  # weighted sum 12: remainder 1 gives check digit 0
    ],
)
def test_valid_icos(ico):
    assert ico_is_valid(ico)
    assert Ico(ico).value == ico


@pytest.mark.parametrize(
    "ico", ["00305864", "00000000", "00000061", "0030586", "003058630", "0030586a", "", "  "]
)
def test_invalid_icos(ico):
    assert not ico_is_valid(ico)
    with pytest.raises(ValidationFailed) as raised:
        Ico(ico)
    assert raised.value.errors[0].field == "ico"


def test_an_ico_is_parsed_as_people_type_it():
    assert Ico.parse(" 0030 5863 ").value == "00305863"
    assert Ico.parse("305863").value == "00305863"  # an old six-digit IČO


def test_a_parsed_ico_names_the_callers_field():
    with pytest.raises(ValidationFailed) as raised:
        Ico.parse("12345678", field="supplier.ico")
    assert raised.value.errors[0].field == "supplier.ico"


@given(st.text(alphabet="0123456789", min_size=7, max_size=7))
def test_exactly_one_check_digit_completes_seven_digits(prefix):
    assert sum(ico_is_valid(prefix + str(d)) for d in range(10)) == 1


# --- IBAN --------------------------------------------------------------------------------

SK = "SK3112000000198742637541"  # the Slovak example of the IBAN registry
CZ = "CZ6508000000192000145399"


@pytest.mark.parametrize("iban", [SK, CZ, "GB82WEST12345698765432"])
def test_valid_ibans(iban):
    assert iban_is_valid(iban)
    assert Iban(iban).value == iban


@pytest.mark.parametrize(
    "iban",
    [
        "SK3112000000198742637542",  # one digit changed
        "SK31120000001987426375",  # too short for SK
        "SK311200000019874263754100",  # too long for SK
        "sk3112000000198742637541",  # not compact: Iban.parse normalises, the check does not
        "SK31 1200 0000 1987 4263 7541",
        "1131120000001987426375",
        "",
    ],
)
def test_invalid_ibans(iban):
    assert not iban_is_valid(iban)
    with pytest.raises(ValidationFailed):
        Iban(iban)


def test_an_iban_is_parsed_as_printed_and_formatted_in_groups_of_four():
    iban = Iban.parse("sk31 1200 0000 1987 4263 7541")
    assert iban.value == SK
    assert iban.formatted == "SK31 1200 0000 1987 4263 7541"


@given(st.integers(min_value=4, max_value=len(SK) - 1), st.integers(min_value=1, max_value=9))
def test_mod_97_catches_every_single_digit_error(position, shift):
    digit = (int(SK[position]) + shift) % 10
    assert not iban_is_valid(SK[:position] + str(digit) + SK[position + 1 :])


# --- Money -------------------------------------------------------------------------------


@given(st.integers(min_value=-(10**13), max_value=10**13))
def test_cents_round_trip(cents):
    assert Money.from_cents(cents).cents == cents


@given(st.decimals(min_value=-(10**11), max_value=10**11, places=2, allow_nan=False))
def test_amounts_round_trip_through_cents(amount):
    money = Money(amount)
    assert Money.from_cents(money.cents) == money
    assert Money.from_cents(money.cents).amount == amount


def test_an_amount_is_kept_to_the_cent():
    assert Money(Decimal("93.7")).amount == Decimal("93.70")
    assert str(Money(Decimal("93.710"))) == "93.71 EUR"
    assert Money(Decimal("93.71")).cents == 9371


@pytest.mark.parametrize(
    "amount", [Decimal("0.001"), Decimal("NaN"), Decimal("Infinity"), 93.71, "93.71"]
)
def test_invalid_amounts_are_refused(amount):
    with pytest.raises(ValidationFailed):
        Money(amount)


def test_money_adds_only_the_same_currency():
    assert Money(Decimal("1.10")) + Money(Decimal("2.20")) == Money(Decimal("3.30"))
    assert Money(Decimal("1.10")) - Money(Decimal("2.20")) == Money(Decimal("-1.10"))
    with pytest.raises(ValidationFailed):
        Money(Decimal("1"), "EUR") + Money(Decimal("1"), "CZK")
    with pytest.raises(ValidationFailed):
        Money(Decimal("1"), "eur")
