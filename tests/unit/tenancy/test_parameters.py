"""`CustomerParameters` validate exactly as today's `EntityContext` does."""

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from riso import paths
from riso.contracts import EntityContext
from riso.shared import ValidationFailed
from riso.tenancy.domain import CustomerParameters

BOLDOG = json.loads((paths.ENTITIES_DIR / "00305863.json").read_text(encoding="utf-8"))
VALUES = {k: BOLDOG[k] for k in CustomerParameters.FIELDS}


def test_boldogs_settings_load_and_round_trip_to_the_entity_context():
    parameters = CustomerParameters.parse("c1", 2026, VALUES)
    assert parameters.values() == VALUES
    context = parameters.entity_context(
        ico="00305863", name="Obec Boldog", reference_period="2026-08"
    )
    assert context == EntityContext(**BOLDOG)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("default_zdroj", "x41"),
        ("default_zdroj", ""),
        ("default_dal", "321000"),
        ("canteen_dal", "321 08"),
        ("vat_payer", "maybe"),
    ],
)
def test_a_bad_value_is_a_field_error(field, value):
    with pytest.raises(ValidationFailed) as caught:
        CustomerParameters.parse("c1", 2026, {**VALUES, field: value})
    assert [e.field for e in caught.value.errors] == [field]


def test_missing_and_unknown_fields_are_refused():
    without = {k: v for k, v in VALUES.items() if k != "canteen_series"}
    with pytest.raises(ValidationFailed) as caught:
        CustomerParameters.parse("c1", 2026, without)
    assert [e.field for e in caught.value.errors] == ["canteen_series"]
    with pytest.raises(ValidationFailed) as caught:
        CustomerParameters.parse("c1", 2026, {**VALUES, "ico": "00305863"})
    assert [e.field for e in caught.value.errors] == ["ico"]


@pytest.mark.parametrize("year", [1999, 2101])
def test_the_year_is_bounded(year):
    with pytest.raises(ValidationFailed) as caught:
        CustomerParameters.parse("c1", year, VALUES)
    assert caught.value.errors[0].field == "year"


TEXT = st.one_of(
    st.sampled_from(["41", "72f", "1AA", "x1", "", "321 000", "321000", "2026-08", "2026-00"]),
    st.text(max_size=8),
)
VALUE = st.one_of(TEXT, st.booleans(), st.integers(-2, 2), st.none())


@settings(max_examples=300)
@given(st.fixed_dictionaries({k: VALUE for k in CustomerParameters.FIELDS}))
def test_validation_equals_the_entity_contexts(values):
    try:
        EntityContext.model_validate(
            {
                "ico": "00305863",
                "name": "Obec Boldog",
                "budget_year": 2026,
                "reference_period": "2026-08",
                **values,
            }
        )
        expected = None
    except ValidationError as exc:
        expected = sorted(".".join(map(str, e["loc"])) for e in exc.errors())
    try:
        CustomerParameters.parse("c1", 2026, values)
        found = None
    except ValidationFailed as exc:
        found = sorted(e.field for e in exc.errors)
    assert found == expected


def test_the_period_is_not_a_parameter():
    with pytest.raises(ValidationFailed) as caught:
        CustomerParameters.parse("c1", 2026, {**VALUES, "reference_period": "2026-08"})
    assert [e.field for e in caught.value.errors] == ["reference_period"]
