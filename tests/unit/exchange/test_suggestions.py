"""Header signatures and mapping suggestions (P2-M3-T02)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from riso.exchange.domain.mapping import (
    ColumnMapping,
    FieldSource,
    ImportType,
    Split,
    Trim,
    ZeroPad,
)
from riso.exchange.domain.records import map_table
from riso.exchange.domain.suggestions import (
    header_signature,
    normalise_header,
    resolve_columns,
    suggest_mapping,
)
from riso.exchange.domain.table import Table

CHART_HEADER = ["SU", "AU", "Typ účtu", "Zarad. SÚV", "Zarad. VZaS", "Činnosť", "Popis"]
BUDGET_HEADER = ["Kód", "Zdroj", "Oddiel", "Trieda", "Analytika", "Popis"]
SERIES_HEADER = ["Evidenčné číslo", "Vzor dokladu", "Popis", "Bankový účet"]


def _columns(mapping: ColumnMapping) -> dict[str, str | None]:
    return {name: source.column for name, source in mapping.fields.items()}


def test_normalised_headers():
    assert normalise_header("  Typ  účtu: ") == "typ uctu"
    assert normalise_header("Zarad. SÚV") == "zarad suv"
    assert normalise_header("---") == ""


def test_the_signature_ignores_order_case_diacritics_and_spacing():
    one = header_signature(CHART_HEADER)
    assert header_signature(reversed(CHART_HEADER)) == one
    assert header_signature([h.upper() for h in CHART_HEADER]) == one
    assert header_signature(["su", "au", "typ  uctu", "zarad suv", "zarad vzas", "cinnost",
                             "popis", ""]) == one  # fmt: skip
    assert header_signature(BUDGET_HEADER) != one
    assert len(one) == 16


@given(st.lists(st.text(max_size=8), max_size=8), st.randoms())
def test_the_signature_is_stable_under_any_shuffle(headers, random):
    shuffled = list(headers)
    random.shuffle(shuffled)
    assert header_signature(shuffled) == header_signature(headers)


def test_topset_chart_headers_suggest_the_chart_mapping():
    table = Table.from_rows([CHART_HEADER, [518, 1, "Nákladový", None, None, None, "x"]])
    mapping = suggest_mapping(table, ImportType.ACCOUNTS)
    assert _columns(mapping) == {
        "su": "SU",
        "au": "AU",
        "type": "Typ účtu",
        "activity": "Činnosť",
        "description": "Popis",
    }
    assert mapping.fields["su"].transforms == (Trim(), ZeroPad(width=3))
    assert mapping.fields["description"].transforms == (Trim(),)
    (record,) = map_table(table, mapping).records
    assert record.key == "518 001" and record.values["type"] == "cost"


@pytest.mark.parametrize("import_type", [ImportType.BUDGET_EXPENSE, ImportType.BUDGET_INCOME])
def test_topset_budget_headers_suggest_the_budget_mapping(import_type):
    table = Table.from_rows([BUDGET_HEADER, [632001, 41, 1, 110, 0, "Energie"]])
    mapping = suggest_mapping(table, import_type)
    assert _columns(mapping) == {
        "ek": "Kód",
        "zdroj": "Zdroj",
        "oddiel": "Oddiel",
        "trieda": "Trieda",
        "analytika": "Analytika",
        "description": "Popis",
    }
    assert map_table(table, mapping).records[0].key == "632001 41 01 110 000"


def test_topset_series_headers_suggest_the_series_mapping():
    mapping = suggest_mapping(Table.from_rows([SERIES_HEADER]), ImportType.DOCUMENT_SERIES)
    assert _columns(mapping) == {
        "series_id": "Evidenčné číslo",
        "pattern": "Vzor dokladu",
        "description": "Popis",
        "bank_account": "Bankový účet",
    }


def test_english_and_odd_headers():
    table = Table.from_rows([["NAME ", "Code:", "Remarks"], ["Energie", "632", "-"]])
    assert _columns(suggest_mapping(table, ImportType.EK)) == {"code": "Code:", "name": "NAME"}
    budget = Table.from_rows([["Ekonomická klasifikácia (EK)", "Zdroj financ.", "Text položky"]])
    assert _columns(suggest_mapping(budget, ImportType.BUDGET_INCOME)) == {
        "ek": "Ekonomická klasifikácia (EK)",
        "zdroj": "Zdroj financ.",
        "description": "Text položky",
    }


def test_nothing_is_suggested_for_unrelated_headers():
    table = Table.from_rows([["Meno", "Priezvisko", "Telefón"], ["a", "b", "c"]])
    assert suggest_mapping(table, ImportType.ACCOUNTS).fields == {}


def test_each_column_serves_one_field():
    # 'Analytika' suits the chart's AU; it must not also be taken for anything else.
    table = Table.from_rows([["SU", "Analytika", "Popis"], ["518", "001", "x"]])
    mapping = suggest_mapping(table, ImportType.ACCOUNTS)
    assert _columns(mapping) == {"su": "SU", "au": "Analytika", "description": "Popis"}


def test_a_composite_budget_key_is_split():
    rows = [
        ["Rozpočtová položka", "Názov"],
        ["637005 41 01 110 000", "Špeciálne služby"],
        ["312001  11H 012", "Dotácia"],  # an income key, extra space
    ]
    mapping = suggest_mapping(Table.from_rows(rows), ImportType.BUDGET_INCOME)
    assert {n: s.column for n, s in mapping.fields.items()} == {
        "ek": "Rozpočtová položka",
        "zdroj": "Rozpočtová položka",
        "oddiel": "Rozpočtová položka",
        "trieda": "Rozpočtová položka",
        "analytika": "Rozpočtová položka",
        "description": "Názov",
    }
    assert mapping.fields["oddiel"].transforms == (
        Trim(),
        Split(index=2, count=5),
        ZeroPad(width=2),
    )
    keys = [r.key for r in map_table(Table.from_rows(rows), mapping).records]
    assert keys == ["637005 41 01 110 000", "312001 11H 012"]


def test_a_composite_account_key_is_split():
    rows = [["Účet", "Druh", "Názov účtu"], ["518 001", "Nákladový", "Telefóny"]]
    table = Table.from_rows(rows)
    mapping = suggest_mapping(table, ImportType.ACCOUNTS)
    assert _columns(mapping) == {
        "su": "Účet",
        "au": "Účet",
        "type": "Druh",
        "description": "Názov účtu",
    }
    (record,) = map_table(table, mapping).records
    assert record.key == "518 001" and record.values["type"] == "cost"


def test_a_template_reads_a_file_whose_headers_differ_in_case():
    template = ColumnMapping(
        import_type=ImportType.EK,
        fields={"code": FieldSource(column="Kód"), "name": FieldSource(column="Názov")},
    )
    table = Table.from_rows([["KOD", "nazov "], ["632", "Energie"]])
    resolved = resolve_columns(template, table)
    assert _columns(resolved) == {"code": "KOD", "name": "nazov"}
    assert map_table(table, resolved).records[0].key == "632"
    unrelated = resolve_columns(template, Table.from_rows([["x", "y"]]))
    assert _columns(unrelated) == {"code": "Kód", "name": "Názov"}
