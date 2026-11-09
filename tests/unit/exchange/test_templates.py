"""Mapping templates (P2-M3-T04): scope rules, the choice by signature, and the built-in
TOPSET templates reading TOPSET-shaped sheets exactly as `riso ingest` reads them (synthetic
rows here; the real exports in tests/integration/test_topset_import.py)."""

from datetime import UTC, datetime, timedelta

import pytest

from riso.codelists.domain import ListKind, parse_entry
from riso.contracts import IngestWarning
from riso.exchange.domain.mapping import ColumnMapping, FieldSource, ImportType
from riso.exchange.domain.records import map_table
from riso.exchange.domain.suggestions import header_signature
from riso.exchange.domain.table import Table
from riso.exchange.domain.templates import (
    BUILTIN,
    TOPSET_BUDGET_HEADER,
    TOPSET_CHART_HEADER,
    TOPSET_SERIES_HEADER,
    MappingTemplate,
    TemplateSaved,
    TemplateScope,
    builtin_for,
    choose_template,
)
from riso.ingest import build
from riso.shared import InvalidState, ValidationFailed

T0 = datetime(2026, 11, 9, tzinfo=UTC)
CODES = ColumnMapping(
    import_type=ImportType.EK,
    fields={"code": FieldSource(column="code"), "name": FieldSource(column="name")},
)
CHART = ColumnMapping(import_type=ImportType.ACCOUNTS, fields={"su": FieldSource(column="SU")})


def _template(template_id, scope, owner, *, mapping=CHART, signature="s1", at=T0):
    return MappingTemplate.create(
        template_id, scope, owner, f"šablóna {template_id}", signature, mapping, at=at, actor="u"
    )


def test_a_template_needs_the_owner_its_scope_names():
    template = _template("t1", TemplateScope.CUSTOMER, "c1")
    assert template.events == [
        TemplateSaved("t1", TemplateScope.CUSTOMER, "c1", ImportType.ACCOUNTS)
    ]
    _template("t2", TemplateScope.PROVIDER, "p1")
    _template("t3", TemplateScope.GLOBAL, None)
    with pytest.raises(InvalidState, match="needs owner"):
        _template("t4", TemplateScope.CUSTOMER, None)
    with pytest.raises(InvalidState, match="has no owner"):
        _template("t5", TemplateScope.GLOBAL, "c1")
    with pytest.raises(InvalidState, match="come with the code"):
        _template("t6", TemplateScope.BUILTIN, None)
    with pytest.raises(InvalidState, match="global lists are global"):
        _template("t7", TemplateScope.CUSTOMER, "c1", mapping=CODES)


@pytest.mark.parametrize(("name", "code"), [("  ", "missing"), ("x" * 121, "string_too_long")])
def test_a_template_needs_a_name(name, code):
    with pytest.raises(ValidationFailed) as caught:
        MappingTemplate.create("t", TemplateScope.GLOBAL, None, name, "s", CHART, at=T0, actor=None)
    assert caught.value.errors[0].code == code


def test_updating_keeps_the_type_and_refuses_built_ins():
    template = _template("t1", TemplateScope.CUSTOMER, "c1")
    template.update(" Nový  názov ", "s2", CHART, T0 + timedelta(days=1))
    assert (template.name, template.signature) == ("Nový názov", "s2")
    assert template.updated_at == T0 + timedelta(days=1)
    with pytest.raises(InvalidState, match="takes a accounts mapping"):
        template.update("x", "s2", CODES, T0)
    with pytest.raises(InvalidState, match="cannot change"):
        BUILTIN["builtin:topset-chart"].update("x", "s", CHART, T0)


def test_the_narrowest_scope_then_the_newest_wins():
    builtin = BUILTIN["builtin:topset-chart"]
    signature = builtin.signature
    glob = _template("g", TemplateScope.GLOBAL, None, signature=signature)
    provider = _template("p", TemplateScope.PROVIDER, "p1", signature=signature)
    old = _template("c-old", TemplateScope.CUSTOMER, "c1", signature=signature)
    new = _template(
        "c-new", TemplateScope.CUSTOMER, "c1", signature=signature, at=T0 + timedelta(1)
    )
    other = _template("x", TemplateScope.CUSTOMER, "c1", signature="other")
    pick = lambda found: choose_template(found, ImportType.ACCOUNTS, signature)  # noqa: E731
    assert pick([builtin]) is builtin
    assert pick([builtin, glob]) is glob
    assert pick([builtin, glob, provider]) is provider
    assert pick([builtin, glob, provider, old, new, other]) is new
    assert choose_template([builtin, glob], ImportType.BUDGET_EXPENSE, signature) is None
    assert choose_template([other], ImportType.ACCOUNTS, "none") is None


def test_the_built_ins():
    assert sorted(BUILTIN) == [
        "builtin:global-cofog",
        "builtin:global-ek",
        "builtin:global-framework_accounts",
        "builtin:global-funding_sources",
        "builtin:topset-chart",
        "builtin:topset-expense",
        "builtin:topset-income",
        "builtin:topset-series",
    ]
    assert all(t.builtin and t.owner_id is None for t in BUILTIN.values())
    assert [t.id for t in builtin_for(ImportType.BUDGET_INCOME)] == ["builtin:topset-income"]
    # The expense and income exports share their headers; the import type tells them apart.
    expense, income = BUILTIN["builtin:topset-expense"], BUILTIN["builtin:topset-income"]
    assert expense.signature == income.signature == header_signature(TOPSET_BUDGET_HEADER)
    assert BUILTIN["builtin:topset-chart"].signature == header_signature(TOPSET_CHART_HEADER)


# The TOPSET templates read as riso ingest reads -------------------------------------------

TITLE = ["UctovnyRozvrh, Obdobie: 08. 2026. IČO: 00305863", *[None] * 6]
ENTITY = ["Obec Vzorová, Hlavná 1, 900 01 Vzorová", *[None] * 6]
CHART_ROWS = [
    TITLE,
    ENTITY,
    list(TOPSET_CHART_HEADER),
    [11, 0, "Aktívny", "x", "y", None, "Softvér"],
    [518, 1, "Nákladový", None, None, 1, " Telefóny "],
    [None] * 7,
    [518, 1, "Nákladový", None, None, None, "Opakovaný"],
    [602, 3, "Výnosový", None, None, "2", None],  # the readers turn 3.0 into 3
    [221, 0, "Aktívny", None, None, None, "Bankový účet"],
    [341, 0, "Pasívny", None, None, None, None],
]
EXPENSE_ROWS = [
    list(TOPSET_BUDGET_HEADER),
    [632001, 41, 1, 110, 0, "Energie"],
    [637004, 41, 4, 510, 1, "Odvoz odpadu"],
    [637004, "41", "04", "510", "001", "Vývoz TKO"],
    [None] * 6,
    [637004, 41, 4, 510, 1, None],
    [611000, "72f", 9, 111, 0, None],
    [717001, "1AA1", 8, 200, 2, "Investícia"],
]
INCOME_ROWS = [
    list(TOPSET_BUDGET_HEADER),
    [312001, "11H", None, None, 12, "Dotácia"],
    [133001, 41, None, None, 0, "Daň za psa"],
    [133001, 41, None, None, 0, None],
]
SERIES_ROWS = [
    list(TOPSET_SERIES_HEADER),
    [1, "FD/XXX/RR", "Došlé faktúry", None],
    ["7", "FDŠJ/XXX/RR", None, "SK31 1200 0000 1987 4263 7541"],
]


def _imported(template_id, rows, kind):
    template = BUILTIN[template_id]
    table = Table.from_rows(rows)
    assert header_signature(table.headers) == template.signature
    mapped = map_table(table, template.mapping)
    assert mapped.errors == ()
    entries = [parse_entry(kind, record.values).to_contract() for record in mapped.records]
    warnings = [
        IngestWarning(
            code=w.code, source=build_source(template_id), rows=list(w.rows), message=w.message
        )
        for w in mapped.warnings
    ]
    return entries, warnings, mapped


def build_source(template_id):
    return {
        "builtin:topset-chart": build.CHART_FILE,
        "builtin:topset-expense": build.EXPENSE_FILE,
        "builtin:topset-income": build.INCOME_FILE,
        "builtin:topset-series": build.SERIES_FILE,
    }[template_id]


def test_the_chart_template_reads_like_riso_ingest():
    expected_warnings: list[IngestWarning] = []
    expected = build._accounts(CHART_ROWS, expected_warnings)
    entries, warnings, mapped = _imported("builtin:topset-chart", CHART_ROWS, ListKind.ACCOUNTS)
    assert entries == expected
    assert warnings == expected_warnings
    assert [w.code for w in warnings] == ["duplicate_key", "missing_description"]
    assert (mapped.facts.ico, mapped.facts.period) == ("00305863", "2026-08")
    assert build._chart_entity(CHART_ROWS)[1] == mapped.facts.period


@pytest.mark.parametrize(
    ("template_id", "rows", "kind", "with_function"),
    [
        ("builtin:topset-expense", EXPENSE_ROWS, ListKind.BUDGET_EXPENSE, True),
        ("builtin:topset-income", INCOME_ROWS, ListKind.BUDGET_INCOME, False),
    ],
)
def test_the_budget_templates_read_like_riso_ingest(template_id, rows, kind, with_function):
    expected_warnings: list[IngestWarning] = []
    expected = build._budget_positions(
        rows, build_source(template_id), expected_warnings, with_function=with_function
    )
    entries, warnings, _ = _imported(template_id, rows, kind)
    assert entries == expected
    assert warnings == expected_warnings
    assert {w.code for w in warnings} == {"duplicate_key", "missing_description"}


def test_the_series_template_reads_like_riso_ingest():
    expected_warnings: list[IngestWarning] = []
    expected = build._document_series(SERIES_ROWS, expected_warnings)
    entries, warnings, _ = _imported("builtin:topset-series", SERIES_ROWS, ListKind.DOCUMENT_SERIES)
    assert entries == expected and warnings == expected_warnings == []
