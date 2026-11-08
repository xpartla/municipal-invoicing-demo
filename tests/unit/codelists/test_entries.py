"""Code list entries validate through the reference contracts and round-trip to them."""

from decimal import Decimal

import pytest

from riso import paths
from riso.codelists.domain import (
    AccountEntry,
    BudgetEntry,
    CofogEntry,
    CostCentreEntry,
    ListKind,
    SeriesEntry,
    TransferEntry,
    entry_fields,
    parse_entry,
)
from riso.contracts import ReferenceBundle
from riso.shared import ValidationFailed

BUNDLE = ReferenceBundle.model_validate_json(
    (paths.BUNDLES_DIR / "00305863" / "2026-08.json").read_bytes()
)


def _fields(error: ValidationFailed) -> list[str]:
    return [e.field for e in error.errors]


def test_every_entry_of_boldogs_bundle_round_trips_to_its_contract():
    assert [AccountEntry.of(a).to_contract() for a in BUNDLE.accounts] == BUNDLE.accounts
    for positions in (BUNDLE.budget_positions_expense, BUNDLE.budget_positions_income):
        assert [BudgetEntry.of(p).to_contract() for p in positions] == positions
    assert [SeriesEntry.of(s).to_contract() for s in BUNDLE.document_series] == (
        BUNDLE.document_series
    )
    assert [TransferEntry.of(t).to_contract() for t in BUNDLE.transfers] == BUNDLE.transfers


def test_an_account_is_parsed_with_its_key_derived():
    entry = parse_entry(ListKind.ACCOUNTS, {"su": "518", "au": "003", "type": "cost"})
    assert entry == AccountEntry("518", "003", "cost")
    assert entry.key == "518 003"
    assert entry.to_contract().row is None


def test_a_given_key_must_match_the_parts():
    with pytest.raises(ValidationFailed):
        parse_entry(ListKind.ACCOUNTS, {"key": "518 004", "su": "518", "au": "003", "type": "cost"})
    with pytest.raises(ValidationFailed):
        parse_entry(
            ListKind.BUDGET_EXPENSE,
            {
                "key": "632005 41 01 110 000",
                "ek": "632005",
                "zdroj": "41",
                "oddiel": "01",
                "trieda": "110",
                "analytika": "001",
            },
        )


@pytest.mark.parametrize(
    ("values", "field"),
    [
        ({"su": "51", "au": "003", "type": "cost"}, "su"),
        ({"su": "518", "au": "3", "type": "cost"}, "au"),
        ({"su": "518", "au": "003", "type": "expense"}, "type"),
        ({"su": "518", "au": "003", "type": "cost", "colour": "red"}, "colour"),
        ({"su": "518", "au": "003", "type": "cost", "active": "yes"}, "active"),
    ],
)
def test_a_bad_account_field_is_named(values, field):
    with pytest.raises(ValidationFailed) as caught:
        parse_entry(ListKind.ACCOUNTS, values)
    assert field in _fields(caught.value)


EXPENSE = {"ek": "632005", "zdroj": "41", "oddiel": "01", "trieda": "110", "analytika": "000"}


def test_a_budget_position_takes_optional_amounts_to_the_cent():
    entry = parse_entry(ListKind.BUDGET_EXPENSE, {**EXPENSE, "approved": "1200.5", "adjusted": 900})
    assert isinstance(entry, BudgetEntry)
    assert entry.key == "632005 41 01 110 000"
    assert entry.function == "01 110"
    assert (entry.approved, entry.adjusted) == (Decimal("1200.50"), Decimal("900.00"))
    assert parse_entry(ListKind.BUDGET_EXPENSE, EXPENSE).approved is None


@pytest.mark.parametrize("amount", ["12.345", "abc", "NaN"])
def test_a_budget_amount_has_at_most_two_decimals(amount):
    with pytest.raises(ValidationFailed) as caught:
        parse_entry(ListKind.BUDGET_EXPENSE, {**EXPENSE, "approved": amount})
    assert _fields(caught.value) == ["approved"]


def test_an_expense_position_needs_its_function_and_an_income_one_does_not():
    without = {k: v for k, v in EXPENSE.items() if k not in ("oddiel", "trieda")}
    with pytest.raises(ValidationFailed) as caught:
        parse_entry(ListKind.BUDGET_EXPENSE, without)
    assert _fields(caught.value) == ["oddiel"]
    income = parse_entry(ListKind.BUDGET_INCOME, {**without, "ek": "111003"})
    assert income.key == "111003 41 000"


def test_oddiel_and_trieda_come_together():
    with pytest.raises(ValidationFailed):
        parse_entry(ListKind.BUDGET_INCOME, {**EXPENSE, "trieda": None})


def test_series_transfers_and_cost_centres_parse():
    series = parse_entry(
        ListKind.DOCUMENT_SERIES,
        {"code": "FD", "series_id": "1", "pattern": "FD/XXX/RR", "description": "Faktúry"},
    )
    assert series.key == "FD"
    transfer = parse_entry(
        ListKind.TRANSFERS, {"id": "312001 111 000", "name": "Voľby", "zdroj": "111"}
    )
    assert isinstance(transfer, TransferEntry)
    assert (transfer.key, transfer.mock) == ("312001 111 000", False)
    assert parse_entry(ListKind.COST_CENTRES, {"code": "01", "name": "OcÚ"}) == CostCentreEntry(
        "01", "OcÚ"
    )
    with pytest.raises(ValidationFailed):
        parse_entry(ListKind.COST_CENTRES, {"code": " ", "name": "x"})


@pytest.mark.parametrize(
    ("kind", "code", "valid"),
    [
        (ListKind.EK, "632", True),
        (ListKind.EK, "632001", True),
        (ListKind.EK, "6320", False),
        (ListKind.EK, "63", False),
        (ListKind.COFOG, "01", True),
        (ListKind.COFOG, "09.6.0.1", True),
        (ListKind.COFOG, "01.1.1", True),
        (ListKind.COFOG, "01 110", False),
        (ListKind.COFOG, "1.1", False),
        (ListKind.FUNDING_SOURCES, "41", True),
        (ListKind.FUNDING_SOURCES, "1AD1", True),
        (ListKind.FUNDING_SOURCES, "72f", True),
        (ListKind.FUNDING_SOURCES, "1", True),
        (ListKind.FUNDING_SOURCES, "A1", False),
        (ListKind.FRAMEWORK_ACCOUNTS, "5", True),
        (ListKind.FRAMEWORK_ACCOUNTS, "518", True),
        (ListKind.FRAMEWORK_ACCOUNTS, "5180", False),
    ],
)
def test_global_codes_follow_their_classification(kind, code, valid):
    values = {"code": code, "name": "  Názov  položky "}
    if valid:
        entry = parse_entry(kind, values)
        assert (entry.key, entry.name) == (code, "Názov položky")
    else:
        with pytest.raises(ValidationFailed) as caught:
            parse_entry(kind, values)
        assert _fields(caught.value) == ["code"]


def test_a_global_entry_needs_a_name():
    with pytest.raises(ValidationFailed) as caught:
        parse_entry(ListKind.EK, {"code": "632", "name": "  "})
    assert _fields(caught.value) == ["name"]


@pytest.mark.parametrize(
    ("code", "oddiel", "trieda"),
    [("01", "01", None), ("01.1", "01", "100"), ("01.1.1", "01", "110"), ("09.6.0.1", "09", "601")],
)
def test_a_cofog_code_gives_the_budget_keys_oddiel_and_trieda(code, oddiel, trieda):
    entry = CofogEntry(code, "x")
    assert (entry.oddiel, entry.trieda) == (oddiel, trieda)


def test_entry_fields_leave_the_derived_key_out():
    assert entry_fields(ListKind.ACCOUNTS) == (
        "su",
        "au",
        "type",
        "activity",
        "description",
        "row",
        "active",
    )
    assert entry_fields(ListKind.EK) == ("code", "name", "active")


def test_a_failing_part_is_reported_without_the_key_derived_from_it():
    with pytest.raises(ValidationFailed) as caught:
        parse_entry(ListKind.ACCOUNTS, {"su": "5", "au": "003", "type": "cost"})
    assert _fields(caught.value) == ["su"]
    with pytest.raises(ValidationFailed) as caught:
        parse_entry(ListKind.BUDGET_EXPENSE, {**EXPENSE, "ek": "63"})
    assert _fields(caught.value) == ["ek"]
