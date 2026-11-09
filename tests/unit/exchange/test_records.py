"""A table through a mapping (P2-M3-T02): values, row errors, the skip and duplicate rules,
and warnings worded as `riso ingest` words them."""

from decimal import Decimal

from riso.exchange.domain.mapping import (
    ColumnMapping,
    DecimalNumber,
    Fact,
    FieldSource,
    ImportType,
    MapValues,
    Split,
    Trim,
    ZeroPad,
)
from riso.exchange.domain.records import RowError, RowWarning, map_table
from riso.exchange.domain.table import Table

PAD3 = (Trim(), ZeroPad(width=3))


def _accounts(**options) -> ColumnMapping:
    return ColumnMapping(
        import_type=ImportType.ACCOUNTS,
        fields={
            "su": FieldSource(column="SU", transforms=PAD3),
            "au": FieldSource(column="AU", transforms=PAD3),
            "type": FieldSource(column="Typ účtu", transforms=(Trim(),)),
            "description": FieldSource(column="Popis", transforms=(Trim(),)),
        },
        **options,
    )


CHART = [
    ["UctovnyRozvrh, Obdobie: 08. 2026. IČO: 305863"],
    ["Obec Boldog"],
    ["SU", "AU", "Typ účtu", "Popis"],
    [518, 1, "Nákladový", " Telefóny "],
    [None, None, None, None],
    [518, 1, "Nákladový", "Ešte raz"],
    [221, 0, "Aktívny", None],
    [None, None, None, "medzisúčet"],
    ["5x8", 2, "Iný", "zlý riadok"],
]


def test_accounts_like_riso_ingest():
    mapped = map_table(Table.from_rows(CHART), _accounts())
    assert [r.key for r in mapped.records] == ["518 001", "221 000"]
    first = mapped.records[0]
    assert first.values == {
        "su": "518",
        "au": "001",
        "type": "cost",
        "activity": None,
        "description": "Telefóny",
        "row": 4,
    }
    assert mapped.records[1].values["type"] == "active"
    assert mapped.rows_read == 5
    assert mapped.warnings == (
        RowWarning("duplicate_key", (4, 6), "account 518 001 appears again; the first row is kept"),
        RowWarning("missing_description", (7,), "1 rows have no Popis"),
        RowWarning("skipped_row", (8,), "1 rows have no key; skipped"),
    )
    assert mapped.errors == (
        RowError(9, "type", "unknown_account_type", "unknown account type 'Iný'"),
    )


def test_rows_without_a_key_are_errors_unless_skipped():
    mapped = map_table(Table.from_rows(CHART), _accounts(skip_empty_key=False))
    assert RowError(8, None, "missing_key", "the row has no key") in mapped.errors


def test_duplicates_can_be_errors():
    mapped = map_table(Table.from_rows(CHART), _accounts(duplicates="error"))
    assert RowError(6, None, "duplicate_key", "account 518 001 repeats row 4") in mapped.errors
    assert not any(w.code == "duplicate_key" for w in mapped.warnings)


def test_a_required_field_left_empty_is_an_error_per_field():
    rows = [["SU", "AU", "Typ účtu", "Popis"], [518, None, None, "x"]]
    mapped = map_table(Table.from_rows(rows), _accounts())
    assert mapped.errors == (
        RowError(2, "au", "missing", "required"),
        RowError(2, "type", "missing", "required"),
    )


def test_facts_from_the_title_row():
    facts = (
        Fact(name="ico", row=1, pattern=r"IČO:\s*(?P<ico>\d{6,8})"),
        Fact(name="period", row=1, pattern=r"Obdobie:\s*(?P<month>\d{1,2})\.\s*(?P<year>\d{4})"),
    )
    mapped = map_table(Table.from_rows(CHART), _accounts(facts=facts))
    assert (mapped.facts.ico, mapped.facts.period) == ("00305863", "2026-08")
    assert mapped.notices == ()

    other = [["Účtovný rozvrh"], ["x"], *CHART[2:]]
    mapped = map_table(Table.from_rows(other), _accounts(facts=facts))
    assert mapped.facts.ico is None and mapped.facts.period is None
    assert [n.code for n in mapped.notices] == ["fact_missing", "fact_missing"]


EXPENSE = [
    ["Kód", "Zdroj", "Oddiel", "Trieda", "Analytika", "Popis", "Suma"],
    [637004, 41, 4, 510, 1, "Odvoz odpadu", "100,50"],
    [632001, 41, 1, 110, 0, None, None],
    [637004, 41, 4, 510, 1, "Vývoz TKO", "20"],
    [637004, 41, 4, 510, 1, "Odvoz odpadu", None],
    [611000, "111", 9, 111, 0, "Plat", "1 000"],
]


def _expense() -> ColumnMapping:
    code = (Trim(), ZeroPad(width=6))
    return ColumnMapping(
        import_type=ImportType.BUDGET_EXPENSE,
        fields={
            "ek": FieldSource(column="Kód", transforms=code),
            "zdroj": FieldSource(column="Zdroj", transforms=(Trim(),)),
            "oddiel": FieldSource(column="Oddiel", transforms=(Trim(), ZeroPad(width=2))),
            "trieda": FieldSource(column="Trieda", transforms=PAD3),
            "analytika": FieldSource(column="Analytika", transforms=PAD3),
            "description": FieldSource(column="Popis", transforms=(Trim(),)),
            "approved": FieldSource(column="Suma", transforms=(DecimalNumber(separator=","),)),
        },
    )


def test_budget_rows_sharing_a_key_merge_into_aliases_like_riso_ingest():
    mapped = map_table(Table.from_rows(EXPENSE), _expense())
    assert [r.key for r in mapped.records] == [
        "637004 41 04 510 001",
        "632001 41 01 110 000",
        "611000 111 09 111 000",
    ]
    merged = mapped.records[0]
    assert merged.rows == (2, 4, 5)
    assert merged.values["description"] == "Odvoz odpadu"
    assert merged.values["aliases"] == ["Vývoz TKO"]
    assert merged.values["rows"] == [2, 4, 5]
    assert merged.values["approved"] == Decimal("120.50")  # the merged rows' amounts add up
    assert mapped.records[1].values["approved"] is None
    assert mapped.records[2].values["approved"] == Decimal("1000")
    assert mapped.warnings == (
        RowWarning(
            "duplicate_key",
            (2, 4, 5),
            "637004 41 04 510 001 appears 3 times; merged, keeping the descriptions "
            "['Odvoz odpadu', 'Vývoz TKO']",
        ),
        RowWarning("missing_description", (3,), "1 rows have no Popis"),
    )
    assert mapped.errors == ()


def test_an_income_key_split_into_parts_leaves_the_function_empty():
    rows = [["Kľúč", "Názov"], ["312001 11H 012", "Dotácia"], ["133001 41 000", "Daň za psa"]]

    def part(index, count=None, pad=None):
        transforms = [Trim(), Split(index=index, count=count)]
        if pad:
            transforms.append(ZeroPad(width=pad))
        return FieldSource(column="Kľúč", transforms=tuple(transforms))

    mapping = ColumnMapping(
        import_type=ImportType.BUDGET_INCOME,
        fields={
            "ek": part(0),
            "zdroj": part(1),
            "oddiel": part(2, 5),
            "trieda": part(3, 5),
            "analytika": part(-1, pad=3),
            "description": FieldSource(column="Názov"),
        },
    )
    mapped = map_table(Table.from_rows(rows), mapping)
    assert [r.key for r in mapped.records] == ["312001 11H 012", "133001 41 000"]
    assert mapped.records[0].values["oddiel"] is None
    assert mapped.records[0].values["aliases"] == []


def test_a_transform_failing_is_a_row_error():
    rows = [EXPENSE[0], [632001, 41, 1, 110, 0, "x", "12,5,3"]]
    mapped = map_table(Table.from_rows(rows), _expense())
    assert mapped.errors == (RowError(2, "approved", "not_a_number", "'12,5,3' is not a number"),)
    assert mapped.records == ()


def test_series_code_comes_from_the_pattern_and_defaults_fill_empty_texts():
    rows = [
        ["Evidenčné číslo", "Vzor dokladu", "Popis", "Bankový účet"],
        ["1", "FD/XXX/RR", "Došlé faktúry", None],
        [None, "FDŠJ/XXX/RR", None, "SK31 1200"],
    ]
    mapping = ColumnMapping(
        import_type=ImportType.DOCUMENT_SERIES,
        fields={
            "series_id": FieldSource(column="Evidenčné číslo", transforms=(Trim(),)),
            "pattern": FieldSource(column="Vzor dokladu", transforms=(Trim(),)),
            "description": FieldSource(column="Popis", transforms=(Trim(),)),
            "bank_account": FieldSource(column="Bankový účet", transforms=(Trim(),)),
        },
    )
    mapped = map_table(Table.from_rows(rows), mapping)
    assert [r.key for r in mapped.records] == ["FD", "FDŠJ"]
    assert mapped.records[1].values == {
        "series_id": "",
        "pattern": "FDŠJ/XXX/RR",
        "code": "FDŠJ",
        "description": "",
        "bank_account": "SK31 1200",
    }


def test_constants_and_value_maps():
    rows = [["Kód", "Druh", "Text"], ["9", "N", "Dotácia"]]
    mapping = ColumnMapping(
        import_type=ImportType.TRANSFERS,
        fields={
            "id": FieldSource(column="Kód"),
            "name": FieldSource(column="Text"),
            "zdroj": FieldSource(constant="41"),
        },
    )
    (record,) = map_table(Table.from_rows(rows), mapping).records
    assert record.values == {"id": "9", "name": "Dotácia", "zdroj": "41", "mock": False}

    accounts = ColumnMapping(
        import_type=ImportType.ACCOUNTS,
        fields={
            "su": FieldSource(constant="518"),
            "au": FieldSource(column="Kód", transforms=PAD3),
            "type": FieldSource(column="Druh", transforms=(MapValues(values={"N": "cost"}),)),
        },
    )
    (record,) = map_table(Table.from_rows(rows), accounts).records
    assert (record.key, record.values["type"]) == ("518 009", "cost")
