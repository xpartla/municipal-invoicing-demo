"""The mapping model and its transforms (P2-M3-T02)."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from riso.codelists.domain import ListKind, entry_fields
from riso.exchange.domain.mapping import (
    SCHEMAS,
    ColumnMapping,
    DateValue,
    DecimalNumber,
    Fact,
    FieldSource,
    ImportType,
    MapValues,
    Split,
    TransformError,
    Trim,
    ZeroPad,
    parse_decimal,
)
from riso.exchange.domain.table import Table
from riso.shared import ValidationFailed


def test_the_target_fields_are_the_code_list_entries_fields():
    for import_type, schema in SCHEMAS.items():
        kind = ListKind(import_type.value)
        produced = set(schema.names) | set(schema.constants)
        if schema.row_field:
            produced.add(schema.row_field)
        if import_type.is_budget:
            produced.add("aliases")
        assert produced <= set(entry_fields(kind)), import_type
        assert schema.key_fields, import_type
    assert {t for t in ImportType if t.is_global} == {
        ImportType.EK,
        ImportType.COFOG,
        ImportType.FUNDING_SOURCES,
        ImportType.FRAMEWORK_ACCOUNTS,
    }


# Transforms -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "result"),
    [(" 41 ", "41"), ("\t\n", None), (None, None), (41, "41"), (Decimal("1.5"), "1.5")],
)
def test_trim(value, result):
    assert Trim().apply(value) == result


@pytest.mark.parametrize(
    ("value", "result"),
    [
        ("1", "001"),
        (1, "001"),
        ("001", "001"),
        ("1234", "1234"),  # longer: left alone, the contract refuses it
        ("1a", "1a"),
        ("", ""),
        (None, None),
        ("١", "١"),  # an Arabic-Indic digit is not padded
    ],
)
def test_zero_pad(value, result):
    assert ZeroPad(width=3).apply(value) == result


@pytest.mark.parametrize(
    ("split", "value", "result"),
    [
        (Split(index=0), "637005 41 01 110 000", "637005"),
        (Split(index=-1), "637005 41 01 110 000", "000"),
        (Split(index=2, count=5), "637005 41 01 110 000", "01"),
        (Split(index=2, count=5), "312001 41 000", None),  # income: no function
        (Split(index=-1), "312001 41 000", "000"),
        (Split(index=1), "  518   001 ", "001"),
        (Split(index=5), "518 001", None),
        (Split(index=-3), "518 001", None),
        (Split(separator="/", index=0), "FD/XXX/RR", "FD"),
        (Split(separator="/", index=1), "FD//RR", "RR"),  # empty parts are dropped
        (Split(separator=r"[-.]", index=1), "01.1-2", "1"),
        (Split(index=0), None, None),
        (Split(index=0), 518, "518"),
    ],
)
def test_split(split, value, result):
    assert split.apply(value) == result


def test_split_refuses_a_bad_pattern():
    with pytest.raises(ValidationError, match="not a valid pattern"):
        Split(separator="(", index=0)


@pytest.mark.parametrize(
    ("value", "separator", "result"),
    [
        ("1 234,56", "auto", Decimal("1234.56")),
        ("1.234,56", "auto", Decimal("1234.56")),
        ("1,234.56", "auto", Decimal("1234.56")),
        ("12,5", "auto", Decimal("12.5")),
        ("12.5", "auto", Decimal("12.5")),
        ("1.234.567", "auto", Decimal("1234567")),
        ("1,234,567", "auto", Decimal("1234567")),
        ("-15,00 €", "auto", Decimal("-15.00")),
        ("1 000,5", "auto", Decimal("1000.5")),
        ("12", "auto", Decimal("12")),
        ("1.500", ",", Decimal("1500")),  # with a decimal comma, a point separates thousands
        ("1,500", ".", Decimal("1500")),
        (12, "auto", Decimal("12")),
        (Decimal("1.25"), "auto", Decimal("1.25")),
        ("", "auto", None),
        (None, "auto", None),
    ],
)
def test_decimal(value, separator, result):
    assert DecimalNumber(separator=separator).apply(value) == result


@pytest.mark.parametrize("value", ["12,5,3.1.1", "abc", "1-2", "--1", date(2026, 1, 1), True])
def test_decimal_refuses_what_is_not_a_number(value):
    with pytest.raises(TransformError) as caught:
        parse_decimal(value)
    assert caught.value.code == "not_a_number"


@given(st.decimals(min_value=-(10**9), max_value=10**9, places=2, allow_nan=False))
def test_decimal_reads_a_slovak_formatted_number_back(number):
    integer, _, fraction = f"{abs(number):.2f}".partition(".")
    groups = f"{int(integer):,}".replace(",", " ")
    text = f"{'-' if number < 0 else ''}{groups},{fraction}"
    assert parse_decimal(text) == number


@pytest.mark.parametrize(
    ("value", "result"),
    [
        ("11.6.2026", date(2026, 6, 11)),
        ("11. 6. 2026", date(2026, 6, 11)),
        ("2026-06-11", date(2026, 6, 11)),
        ("11/06/2026", date(2026, 6, 11)),
        ("11.6.26", date(2026, 6, 11)),
        (datetime(2026, 6, 11, 8, 0), date(2026, 6, 11)),
        (date(2026, 6, 11), date(2026, 6, 11)),
        ("  ", None),
        (None, None),
    ],
)
def test_date(value, result):
    assert DateValue().apply(value) == result


@pytest.mark.parametrize("value", ["31.2.2026", "jún 2026", "2026/13/01"])
def test_date_refuses_what_is_not_a_date(value):
    with pytest.raises(TransformError) as caught:
        DateValue().apply(value)
    assert caught.value.code == "not_a_date"


def test_date_with_chosen_formats():
    assert DateValue(formats=("%m/%d/%Y",)).apply("06/11/2026") == date(2026, 6, 11)


def test_map():
    table = MapValues(values={"Aktívny": "active", "P": "passive"})
    assert table.apply(" aktivny ") == "active"
    assert table.apply("p") == "passive"
    assert table.apply("X") == "X"
    assert table.apply(None) is None
    assert MapValues(values={"A": "active"}, otherwise="empty").apply("X") is None
    with pytest.raises(TransformError) as caught:
        MapValues(values={"A": "active"}, otherwise="error").apply("X")
    assert caught.value.code == "unmapped_value"


# The mapping -----------------------------------------------------------------------------


def test_a_mapping_round_trips_through_json():
    mapping = ColumnMapping(
        import_type=ImportType.BUDGET_EXPENSE,
        fields={
            "ek": FieldSource(column="Kľúč", transforms=(Trim(), Split(index=0))),
            "zdroj": FieldSource(constant="41"),
            "approved": FieldSource(column="Suma", transforms=(DecimalNumber(separator=","),)),
        },
        facts=(Fact(name="period", row=1, pattern=r"(?P<month>\d+)\. (?P<year>\d{4})"),),
    )
    again = ColumnMapping.model_validate_json(mapping.model_dump_json())
    assert again == mapping
    assert again.fields["ek"].transforms[1] == Split(index=0)
    assert mapping.duplicate_rule == "merge"
    assert mapping.source("oddiel").empty


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"import_type": "accounts", "fields": {"ek": {}}}, "not fields of accounts"),
        ({"import_type": "accounts", "duplicates": "merge"}, "only budget positions"),
        (
            {"import_type": "accounts", "fields": {"su": {"column": "SU", "constant": "5"}}},
            "not both",
        ),
        (
            {"import_type": "accounts", "fields": {"su": {"transforms": [{"op": "eval"}]}}},
            "op",
        ),
        (
            {"import_type": "accounts", "facts": [{"name": "ico", "row": 1, "pattern": "x"}]},
            "groups",
        ),
        ({"import_type": "accounts", "unknown": 1}, "Extra inputs"),
    ],
)
def test_a_bad_mapping_is_refused(data, message):
    with pytest.raises(ValidationError, match=message):
        ColumnMapping.model_validate(data)


def test_a_mapping_is_checked_against_the_file():
    table = Table.from_rows([["Title"], ["SU", "AU", "Typ"], ["518", "001", "Nákladový"]])
    mapping = ColumnMapping(
        import_type=ImportType.ACCOUNTS,
        fields={"su": FieldSource(column="SU"), "au": FieldSource(column="Analytika")},
        facts=(Fact(name="ico", row=2, pattern=r"(?P<ico>\d+)"),),
    )
    with pytest.raises(ValidationFailed) as caught:
        mapping.check_against(table)
    assert {(e.field, e.code) for e in caught.value.errors} == {
        ("fields.au.column", "unknown_column"),
        ("fields.type", "missing"),
    }
    # A derived field needs no source: the series code comes from the pattern.
    series = ColumnMapping(
        import_type=ImportType.DOCUMENT_SERIES, fields={"pattern": FieldSource(column="SU")}
    )
    series.check_against(table)
