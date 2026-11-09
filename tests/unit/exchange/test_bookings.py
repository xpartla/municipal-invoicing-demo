"""Past bookings (P2-M3-T05): rows grouped into bookings, parsed through the contracts, planned
against the supplier memory and counters, and merged. Synthetic data; the IČOs are the
dataset's made-up placeholders."""

from datetime import date
from decimal import Decimal

from riso.contracts import Counters, Precedent, PrecedentLine, SupplierMemory, SupplierRecord
from riso.exchange.domain.bookings import (
    CounterRise,
    merge_plan,
    parse_bookings,
    plan_bookings,
)
from riso.exchange.domain.records import map_table
from riso.exchange.domain.suggestions import header_signature, suggest_mapping
from riso.exchange.domain.table import Table
from riso.exchange.domain.templates import BOOKINGS_HEADER, BUILTIN

ENTITY = "00305863"
KOSENIE, KOMINAR, VZOROVA = "11223341", "23456787", "12345679"
GREENERY = "635006 41 06 200 000"
SERVICES = "637004 41 01 110 000"
SERIES = {"FD": "FD/XXX/RR", "FDŠJ": "FDŠJ/XXX/RR"}
POSITIONS = frozenset({GREENERY, SERVICES})
ACCOUNTS = frozenset({"511 000", "518 000", "321 000"})


def _row(ico, number, *, line=(GREENERY, "511 000", "321 000"), name="Tomáš Ukážkový",
         when="26.5.2026", amount="812,50", vs="2026113", texts=("zeleň", "kosenie")):  # fmt: skip
    return [ico, name, number, when, amount, vs, *line, *texts]


def _book(*rows):
    return Table.from_rows([list(BOOKINGS_HEADER), *rows])


def _mapped(table):
    template = BUILTIN["builtin:generic-bookings"]
    assert header_signature(table.headers) == template.signature
    return map_table(table, template.mapping)


def _memory():
    precedent = Precedent(
        document_number="FD/215/26",
        booking_date=date(2026, 7, 24),
        amount=Decimal("1000.00"),
        lines=[
            PrecedentLine(
                budget_key=SERVICES,
                md="518 000",
                dal="321 000",
                budget_text="služby",
                posting_text="účtovníctvo",
            )
        ],  # fmt: skip
        source="screenshot",
    )
    return SupplierMemory(
        entity_ico=ENTITY,
        suppliers=[SupplierRecord(ico=VZOROVA, name="Mária Vzorová", precedents=[precedent])],
    )


def _counters():
    return Counters(entity_ico=ENTITY, last_used={"FD/2026": 120}, used_numbers=["FD/120/26"])


def _plan(table, memory=None, counters=None):
    bookings, problems = parse_bookings(_mapped(table).records)
    assert problems == []
    return plan_bookings(
        bookings,
        memory or _memory(),
        counters or _counters(),
        series=SERIES,
        positions=POSITIONS,
        accounts=ACCOUNTS,
    )


def test_rows_of_one_supplier_and_number_are_the_lines_of_one_booking():
    mapped = _mapped(
        _book(
            _row(KOSENIE, "FD/113/26"),
            _row(KOSENIE, "FD/113/26", line=(SERVICES, "518 000", "321 000"), amount="900"),
            [None] * len(BOOKINGS_HEADER),
            _row(KOMINAR, "FD/113/26", name="Jozef Vzorný"),
            _row("", "FD/114/26"),
        )
    )
    assert [r.key for r in mapped.records] == [f"{KOSENIE} FD/113/26", f"{KOMINAR} FD/113/26"]
    first = mapped.records[0].values
    assert first["rows"] == [2, 3]
    assert [line["budget_key"] for line in first["lines"]] == [GREENERY, SERVICES]
    assert first["amount"] == Decimal("812.50") and first["booking_date"] == date(2026, 5, 26)
    assert "budget_key" not in first and "aliases" not in first
    assert {w.code: w.rows for w in mapped.warnings} == {"booking_differs": (2, 3)}
    assert {(e.row, e.field, e.code) for e in mapped.errors} == {(6, "supplier_ico", "missing")}


def test_a_booking_is_read_through_the_contracts():
    bookings, problems = parse_bookings(
        _mapped(
            _book(
                _row("305863", "FD/1/26", line=(GREENERY, "511000", "321.000")),
                _row(KOSENIE, "FD/2/26", line=("635006 41 6 200 000", "511 000", "321 000")),
                _row(KOSENIE, "FD/3/26", amount="1,005"),
                _row(KOSENIE, "FD/4/26", texts=(None, None), name=None),
            )
        ).records
    )
    assert [b.number for b in bookings] == ["FD/1/26", "FD/4/26"]
    first = bookings[0]
    assert first.supplier_ico == "00305863" and first.precedent.source == "import"
    assert (first.precedent.lines[0].md, first.precedent.lines[0].dal) == ("511 000", "321 000")
    assert bookings[1].supplier_name == KOSENIE  # no name: the IČO, as the engine's feedback
    assert bookings[1].precedent.lines[0].budget_text == ""
    assert {(p.key, p.rows, p.field) for p in problems} == {
        (f"{KOSENIE} FD/2/26", (3,), "budget_key"),
        (f"{KOSENIE} FD/3/26", (4,), "amount"),
    }


def test_the_plan_skips_what_the_memory_has_and_raises_the_counters():
    plan = _plan(
        _book(
            _row(KOSENIE, "FD/113/26"),
            _row(VZOROVA, "FD/215/26", name="Mária Vzorová"),  # in the memory: skipped
            _row(KOMINAR, "FD/120/26", name="Jozef Vzorný"),  # the number is taken
            _row(KOMINAR, "FD/140/26", name="Jozef Vzorný"),
            _row(KOMINAR, "FDŠJ/007/26", name="Jozef Vzorný"),
            _row(KOMINAR, "FD/007/25", name="Jozef Vzorný"),
            _row(KOMINAR, "XY/1/26", line=("611000 41 01 110 000", "999 000", "321 000")),
            _row(KOSENIE, "FD/140/26"),  # the same number for another supplier
            _row(KOSENIE, "FD-9"),
        )
    )
    assert [b.number for b in plan.new] == [
        "FD/113/26", "FD/120/26", "FD/140/26", "FDŠJ/007/26", "FD/007/25", "XY/1/26",
        "FD/140/26", "FD-9",
    ]  # fmt: skip
    assert [b.number for b in plan.present] == ["FD/215/26"]
    assert plan.counters == (
        CounterRise("FD/2025", 0, 7),
        CounterRise("FD/2026", 120, 215),
        CounterRise("FDŠJ/2026", 0, 7),
    )
    assert "FD/120/26" not in plan.numbers and plan.numbers.count("FD/140/26") == 1
    codes = {w.code: w for w in plan.warnings}
    assert set(codes) == {
        "booking_present",
        "number_used",
        "number_repeats",
        "unknown_series",
        "unknown_budget_key",
        "unknown_account",
    }
    assert codes["unknown_budget_key"].key == "611000 41 01 110 000"
    assert codes["unknown_account"].rows == (8,)
    assert {w.key for w in plan.warnings if w.code == "unknown_series"} == {"XY", "FD-9"}
    assert codes["number_repeats"].rows == (5, 9)


def test_a_number_outside_its_pattern_and_a_bad_check_digit_are_warned():
    plan = _plan(_book(_row("11223344", "FD/abc/26"), _row(KOSENIE, "FD/1/2026")))
    assert [(w.code, w.rows) for w in plan.warnings] == [
        ("ico_check_digit", (2,)),
        ("number_not_in_pattern", (2,)),
        ("number_not_in_pattern", (3,)),
    ]
    assert plan.counters == ()


def test_merging_adds_the_precedents_newest_first_and_twice_changes_nothing():
    table = _book(
        _row(VZOROVA, "FD/100/26", name="Mária Vzorová", when="1.6.2026"),
        _row(VZOROVA, "FD/230/26", name="Mária Vzorová", when="30.7.2026"),
        _row(KOSENIE, "FD/113/26"),
        _row(KOSENIE, "FD/113/26", line=(SERVICES, "518 000", "321 000")),
        _row(KOMINAR, "FD/90/26", name="Jozef Vzorný", when=""),
    )
    memory, counters = merge_plan(_plan(table), _memory(), _counters())
    vzorova = memory.find(VZOROVA)
    assert [p.document_number for p in vzorova.precedents] == [
        "FD/230/26",
        "FD/215/26",
        "FD/100/26",
    ]
    assert [p.source for p in vzorova.precedents] == ["import", "screenshot", "import"]
    kosenie = memory.find(KOSENIE)
    assert kosenie.name == "Tomáš Ukážkový" and len(kosenie.precedents[0].lines) == 2
    assert memory.find(KOMINAR).precedents[0].booking_date is None
    assert counters.last_used == {"FD/2026": 230}
    assert counters.used_numbers == ["FD/120/26", "FD/100/26", "FD/230/26", "FD/113/26", "FD/90/26"]
    SupplierMemory.model_validate(memory.model_dump())  # still one record per supplier

    again = _plan(table, memory, counters)
    assert again.new == () and len(again.present) == 4
    assert again.numbers == () and again.counters == ()
    assert merge_plan(again, memory, counters) == (memory, counters)


def test_book_headers_suggest_the_bookings_fields():
    table = Table.from_rows(
        [
            [
                "IČO",
                "Obchodný partner",
                "Číslo dokladu",
                "Dátum",
                "Suma celkom",
                "VS",
                "Rozpočtová položka",
                "MD",
                "Dal",
                "Text",
            ],  # fmt: skip
            [
                "11223341",
                "Tomáš",
                "FD/1/26",
                "1.6.2026",
                "10",
                "1",
                GREENERY,
                "511 000",
                "321 000",
                "x",
            ],  # fmt: skip
        ]
    )
    from riso.exchange.domain.mapping import ImportType

    fields = suggest_mapping(table, ImportType.PAST_BOOKINGS).fields
    assert {name: source.column for name, source in fields.items()} == {
        "supplier_ico": "IČO",
        "supplier_name": "Obchodný partner",
        "document_number": "Číslo dokladu",
        "booking_date": "Dátum",
        "amount": "Suma celkom",
        "variable_symbol": "VS",
        "budget_key": "Rozpočtová položka",
        "md": "MD",
        "dal": "Dal",
        "posting_text": "Text",
    }
