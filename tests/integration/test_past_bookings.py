"""Past bookings through the import tool (P2-M3-T05), on a seeded database: a synthetic book
of 20 rows becomes Boldog's supplier precedents (`source: "import"`) in the database, its
numbers become used and the FD counter rises; the engine then codes a matching invoice by
the imported precedent; importing the same book again adds nothing. The suppliers are the
dataset's made-up sole traders, with their placeholder IČOs."""

import csv
import io

import pytest

from riso.api.composition import build_services
from riso.api.importing import run_import
from riso.audit.domain.event import AuditFilter
from riso.dataset import load_cases
from riso.exchange.domain.mapping import ImportType
from riso.exchange.domain.run import RunState
from riso.exchange.domain.templates import BOOKINGS_HEADER
from riso.identity.application.access import Grant
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.invoicing.application.coding import code_document
from riso.platform import Settings
from riso.shared import RequestContext

PASSWORD = "Ukážkové-heslo-2026"
KOSENIE, KOMINAR, REVIZIE, VZOROVA = "11223341", "23456787", "24680249", "12345679"
GREENERY = "635006 41 06 200 000"
SERVICES = "637004 41 01 110 000"


def _line(ico, name, number, when, amount, vs, key, md, budget_text, posting_text):
    return [ico, name, number, when, amount, vs, key, md, "321 000", budget_text, posting_text]


BOOK = [
    # Tomáš Ukážkový mows the greenery: three bookings, one of two lines.
    _line(KOSENIE, "Tomáš Ukážkový", "FD/090/26", "28. 4. 2026", "812,50", "2026041",
          GREENERY, "511 000", "údržba verejnej zelene", "kosenie 4/2026"),
    _line(KOSENIE, "Tomáš Ukážkový", "FD/101/26", "12. 5. 2026", "1 230,00", "2026052",
          GREENERY, "511 000", "údržba verejnej zelene", "kosenie 5/2026"),
    _line(KOSENIE, "Tomáš Ukážkový", "FD/101/26", "12. 5. 2026", "1 230,00", "2026052",
          SERVICES, "518 000", "všeobecné služby", "odvoz pokoseného"),
    _line(KOSENIE, "Tomáš Ukážkový", "FD/118/26", "2. 6. 2026", "812,50", "2026061",
          GREENERY, "511 000", "údržba verejnej zelene", "kosenie 6/2026"),
    # Jozef Vzorný, the chimney sweep: one booking per quarter, with one line each.
    *(
        _line(KOMINAR, "Jozef Vzorný - KOMINÁR", f"FD/{number}/26", when, "96,00", vs,
              SERVICES, "518 000", "všeobecné služby", text)
        for number, when, vs, text in [
            ("031", "10. 2. 2026", "1001", "čistenie komínov OcÚ"),
            ("077", "14. 4. 2026", "1002", "čistenie komínov KD"),
            ("150", "3. 7. 2026", "1003", "čistenie komínov MŠ"),
        ]
    ),
    # Marek Príkladný, electrical inspections: two bookings of several lines.
    *(
        _line(REVIZIE, "Ing. Marek Príkladný", number, when, amount, "77" + number[3:6],
              SERVICES, "518 000", "všeobecné služby", text)
        for number, when, amount, text in [
            ("FD/055/26", "20. 3. 2026", "450,00", "revízia elektroinštalácie OcÚ"),
            ("FD/055/26", "20. 3. 2026", "450,00", "revízia hromozvodu OcÚ"),
            ("FD/055/26", "20. 3. 2026", "450,00", "revízia elektroinštalácie KD"),
            ("FD/160/26", "15. 7. 2026", "380,00", "revízia elektroinštalácie MŠ"),
            ("FD/160/26", "15. 7. 2026", "380,00", "revízia hromozvodu MŠ"),
        ]
    ),
    # Mária Vzorová's FD/215/26 is in the memory already (a screenshot): skipped.
    _line(VZOROVA, "Mária Vzorová", "FD/215/26", "24. 7. 2026", "1 000,00", "2026072",
          "637005 41 01 110 000", "518 001", "špeciálne služby", "účtovníctvo 5/2026"),
    _line(VZOROVA, "Mária Vzorová", "FD/240/26", "21. 8. 2026", "1 000,00", "2026082",
          "637005 41 01 110 000", "518 001", "špeciálne služby", "účtovníctvo 6/2026"),
    _line(VZOROVA, "Mária Vzorová", "FD/240/26", "21. 8. 2026", "1 000,00", "2026082",
          "637005 41 01 110 000", "518 001", "špeciálne služby", "účtovníctvo 7/2026"),
    # A school canteen invoice, in the canteen's series.
    _line(KOSENIE, "Tomáš Ukážkový", "FDŠJ/004/26", "5. 5. 2026", "120,00", "2026050",
          GREENERY, "511 000", "údržba verejnej zelene", "kosenie dvora ŠJ"),
    # Earlier years: the 2025 counter rises too.
    _line(KOMINAR, "Jozef Vzorný - KOMINÁR", "FD/301/25", "1. 12. 2025", "96,00", "999",
          SERVICES, "518 000", "všeobecné služby", "čistenie komínov OcÚ"),
    _line(REVIZIE, "Ing. Marek Príkladný", "FD/280/25", "10. 11. 2025", "120,00", "998",
          SERVICES, "518 000", "všeobecné služby", "revízia"),
    _line(REVIZIE, "Ing. Marek Príkladný", "FD/280/25", "10. 11. 2025", "120,00", "998",
          SERVICES, "518 000", "všeobecné služby", "revízia KD"),
    _line(REVIZIE, "Ing. Marek Príkladný", "FD/281/25", "11. 11. 2025", "80,00", "997",
          SERVICES, "518 000", "všeobecné služby", "revízia MŠ"),
]  # fmt: skip


def _csv(rows) -> bytes:
    out = io.StringIO()
    csv.writer(out, delimiter=";", lineterminator="\r\n").writerows([BOOKINGS_HEADER, *rows])
    return out.getvalue().encode("windows-1250")


@pytest.fixture
def env(tmp_path, seeded_copy):
    settings = Settings(var_dir=tmp_path / "var", env="test")
    done = seeded_copy(settings.var_dir)
    services = build_services(settings, hasher=Argon2Hasher.fast())
    with services.uow(immediate=False) as uow:
        user = uow.users.get(done.users["user"][0])
        grants = tuple(Grant(m.scope.kind, m.scope.id, m.role) for m in user.active_memberships())
    ctx = RequestContext("test", user.id, policy=services.policy(grants))
    yield services, done.customers["Obec Boldog"], ctx, services.supplier_state()
    services.close()


def _import(services, ctx, boldog, rows=BOOK):
    return run_import(
        services, ctx, boldog, ImportType.PAST_BOOKINGS, 2026, "kniha.csv", _csv(rows)
    )


def _kosenie_invoice():
    case = next(c for c in load_cases() if c.id == "seed-29-kosenie-greenery")
    return case.invoice


def test_a_book_of_20_rows_becomes_precedents_used_numbers_and_counters(env):
    services, boldog, ctx, state = env
    assert len(BOOK) == 20
    before_memory, before_counters = state.memory(boldog), state.counters(boldog)

    run = _import(services, ctx, boldog)
    assert run.template_id == "builtin:generic-bookings"
    assert run.state is RunState.APPLIED and run.version_id is None
    report = run.report
    assert report.errors == ()
    assert (report.rows_read, report.entries) == (20, 14)
    assert (report.diff.added, report.diff.unchanged) == (13, 1)
    assert {w.code for w in report.warnings} == {"booking_present"}
    assert {(c.key, c.before, c.after) for c in report.counters} == {
        ("FD/2026", 222, 240),
        ("FD/2025", 0, 301),
        ("FDŠJ/2026", 0, 4),
    }
    assert report.numbers_used == 13

    memory, counters = state.memory(boldog), state.counters(boldog)
    kosenie = memory.find(KOSENIE)
    assert [p.document_number for p in kosenie.precedents] == [
        "FD/118/26", "FD/101/26", "FDŠJ/004/26", "FD/090/26",
    ]  # fmt: skip
    assert {p.source for p in kosenie.precedents} == {"import"}
    assert [len(p.lines) for p in memory.find(REVIZIE).precedents] == [2, 3, 1, 2]
    vzorova = memory.find(VZOROVA)
    assert [(p.document_number, p.source) for p in vzorova.precedents] == [
        ("FD/240/26", "import"),
        ("FD/215/26", "screenshot"),
    ]
    assert len(memory.suppliers) == len(before_memory.suppliers) + 3
    assert counters.last_used == {"FD/2026": 240, "FDŠJ/2026": 4, "FD/2025": 301}
    assert set(counters.used_numbers) - set(before_counters.used_numbers) == {
        "FD/090/26", "FD/101/26", "FD/118/26", "FD/031/26", "FD/077/26", "FD/150/26",
        "FD/055/26", "FD/160/26", "FD/240/26", "FDŠJ/004/26", "FD/301/25", "FD/280/25",
        "FD/281/25",
    } - {"FD/215/26"}  # fmt: skip
    with services.uow(immediate=False) as uow:
        events, _ = uow.audit_log.page(AuditFilter(customer_id=boldog, action="imports.applied"))
    assert events[0].details["bookings"] == 13 and events[0].details["skipped"] == 1


def test_the_engine_codes_a_matching_invoice_by_the_imported_precedent(env):
    services, boldog, ctx, _ = env
    invoice = _kosenie_invoice()

    def proposal():
        return code_document(
            ctx,
            services.reference_data(),
            services.supplier_state(),
            boldog,
            invoice,
            today=invoice.invoice.issue_date,
        )

    def precedent_evidence(found):
        return [e.detail for e in found.evidence if e.source == "supplier_memory"]

    assert precedent_evidence(proposal()) == []  # no memory of this supplier yet
    _import(services, ctx, boldog)
    coded = proposal()
    assert [b.key for b in coded.budget] == [GREENERY]
    assert [p.md for p in coded.posting] == ["511 000"]
    assert any("FD/118/26 coded 635006 41 06 200 000" in d for d in precedent_evidence(coded))


def test_importing_the_same_book_twice_adds_nothing(env):
    services, boldog, ctx, state = env
    _import(services, ctx, boldog)
    memory, counters = state.memory(boldog), state.counters(boldog)
    again = _import(services, ctx, boldog)
    assert again.state is RunState.APPLIED
    assert (again.report.diff.added, again.report.diff.unchanged) == (0, 14)
    assert again.report.counters == () and again.report.numbers_used == 0
    assert state.memory(boldog) == memory and state.counters(boldog) == counters


def test_a_book_with_bad_rows_does_not_apply(env):
    services, boldog, ctx, state = env
    before = state.memory(boldog)
    bad = [
        BOOK[0],
        _line(KOSENIE, "Tomáš Ukážkový", "FD/300/26", "1.9.2026", "10,00", "1",
              "635006 41 6 200 000", "511 000", "x", "y"),
        _line("", "Bez IČO", "FD/301/26", "1.9.2026", "10,00", "1", GREENERY, "511 000", "", ""),
    ]  # fmt: skip
    run = _import(services, ctx, boldog, bad)
    assert run.state is RunState.DRY_RUN_FAILED
    assert {(e.code, e.rows) for e in run.report.hard_errors} == {
        ("string_pattern_mismatch", (3,)),
        ("missing", (4,)),
    }
    assert state.memory(boldog) == before
