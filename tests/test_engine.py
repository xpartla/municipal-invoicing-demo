"""The deterministic engine, S1 to S8. The M1 exit criterion is the first test: the four
precedents' budget keys, MD and DAL are reproduced exactly from their invoice JSON."""

import datetime as dt
from decimal import Decimal

import pytest

from riso.contracts import CodingProposal, Feedback, InvoiceDocument, SupplierMemory
from riso.dataset import load_cases
from riso.engine import code_invoice
from riso.engine.s8_feedback import apply_feedback
from riso.eval import coded_lines
from riso.knowledge import load_knowledge
from riso.reference import ReferenceIndex
from riso.store import StateStore

BOLDOG = "00305863"
NEW_SUPPLIER = "11111119"  # passes the IČO check digit and is in no supplier memory
ANCHORS = ["anchor-accounting", "anchor-dog-shelter", "anchor-dpo", "anchor-telekom"]


@pytest.fixture(scope="module")
def setting(source, tmp_path_factory):
    state = StateStore(var_dir=tmp_path_factory.mktemp("var"))
    return {
        "entity": source.context(BOLDOG),
        "bundle": source.bundle(BOLDOG),
        "knowledge": load_knowledge(2026),
        "memory": state.supplier_memory(BOLDOG),
        "counters": state.counters(BOLDOG),
    }


def code(document: InvoiceDocument, setting: dict, **state) -> CodingProposal:
    return code_invoice(document, **(setting | state))


def anchor(case_id: str):
    return next(c for c in load_cases() if c.id == case_id)


def invoice(
    case_id: str,
    lines: list[tuple[str, str]],
    *,
    supplier: str = "Vzor, s.r.o.",
    ico: str | None = NEW_SUPPLIER,
    number: str | None = "150",
    booked: dt.date | None = dt.date(2026, 7, 1),
    free_text: tuple[str, ...] = (),
    document_type: str = "invoice",
    vat_payer: bool = False,
    total: str | None = None,
    variable_symbol: str = "20260001",
) -> InvoiceDocument:
    gross = total if total is not None else str(sum(Decimal(amount) for _, amount in lines))
    return InvoiceDocument.model_validate(
        {
            "id": case_id,
            "supplier": {"name": supplier, "ico": ico, "vat_payer": vat_payer},
            "customer": {"name": "Obec Boldog", "ico": BOLDOG},
            "invoice": {
                "number": "2026-001",
                "issue_date": "2026-06-30",
                "variable_symbol": variable_symbol,
                "document_type": document_type,
            },
            "handwritten": {"date": booked.isoformat() if booked else None, "number": number},
            "totals": {"gross": gross},
            "lines": [{"description": text, "gross": amount} for text, amount in lines],
            "free_text": list(free_text),
            "ocr_meta": {"synthetic": True},
        }
    )


@pytest.mark.parametrize("case_id", ANCHORS)
def test_the_four_precedents_are_reproduced_exactly(case_id, setting):
    case = anchor(case_id)
    expected = case.expected.coding

    proposal = code(case.invoice, setting)

    assert coded_lines(proposal.posting, proposal.budget) == coded_lines(
        expected.posting, expected.budget
    )
    assert proposal.document == expected.document
    assert [(b.text, p.text) for b, p in zip(proposal.budget, proposal.posting, strict=True)] == [
        (b.text, p.text) for b, p in zip(expected.budget, expected.posting, strict=True)
    ]
    assert not proposal.needs_review, proposal.review_reasons
    assert proposal.validation.ok
    assert {"keys exist", "sums match", "account types"} <= set(proposal.validation.checks)


@pytest.mark.parametrize("case_id", ["anchor-accounting", "anchor-dog-shelter", "anchor-dpo"])
def test_without_supplier_memory_the_text_alone_finds_the_codes(case_id, setting):
    case = anchor(case_id)

    proposal = code(case.invoice, setting, memory=SupplierMemory(entity_ico=BOLDOG))

    expected = case.expected.coding
    assert coded_lines(proposal.posting, proposal.budget) == coded_lines(
        expected.posting, expected.budget
    )
    assert not proposal.needs_review, proposal.review_reasons
    assert not proposal.supplier.known


def test_without_memory_telekom_is_ambiguous_and_goes_to_review(setting):
    proposal = code(
        anchor("anchor-telekom").invoice, setting, memory=SupplierMemory(entity_ico=BOLDOG)
    )

    assert proposal.budget[0].key == "632005 41 01 110 000"
    assert proposal.needs_review
    assert "several budget positions fit; the best is proposed" in proposal.review_reasons
    alternatives = {a.budget_key: a.md for a in proposal.alternatives}
    assert alternatives["632003 41 01 110 001"] == "518 003"


def test_the_evidence_names_the_precedent_and_the_handwriting(setting):
    proposal = code(anchor("anchor-telekom").invoice, setting)

    details = {(e.field, e.source, e.detail) for e in proposal.evidence}
    assert ("ek", "supplier_memory", "FD/213/26 coded 632005 41 01 110 000 for this IČO") in details
    assert ("booking_date", "handwritten", "23.6.26 written on the scan") in details
    assert ("document_number", "handwritten", "144 written on the scan") in details


def test_a_credit_note_goes_to_manual_entry(setting):
    note = invoice(
        "credit-note",
        [("Dobropis k faktúre 8390051427", "-12.30")],
        supplier="Slovak Telekom, a.s.",
    )

    proposal = code(note, setting)

    assert proposal.posting == [] and proposal.budget == []
    assert proposal.needs_review
    assert "credit note, manual entry" in proposal.review_reasons


def test_canteen_food_follows_the_canteen_rule(setting):
    food = invoice(
        "canteen", [("Mlieko polotučné 1 l", "38.40"), ("Jogurt biely", "12.60")], number="12"
    )

    proposal = code(food, setting)

    assert proposal.document.series == "FDŠJ"
    assert proposal.document.number == "FDŠJ/012/26"
    assert coded_lines(proposal.posting, proposal.budget) == [
        ("633011 72f 09 601 008", "501 080", "321 080")
    ]
    assert "633011 72f 09 601 098" in {a.budget_key for a in proposal.alternatives}
    assert not proposal.needs_review, proposal.review_reasons


def test_a_capital_item_lands_on_an_acquisition_account(setting):
    works = invoice("capital", [("Revitalizácia Lesíka – stavebné práce, 2. etapa", "18450.00")])

    proposal = code(works, setting)

    assert coded_lines(proposal.posting, proposal.budget) == [
        ("717001 41 01 110 018", "042 007", "321 000")
    ]
    assert proposal.validation.ok


def test_entries_naming_different_buildings_are_split(setting):
    telecom = invoice(
        "split",
        [("Hlasové služby OcÚ", "50.00"), ("Hlasové služby MŠ", "43.71")],
        supplier="Slovak Telekom, a.s.",
        ico="35763469",
        vat_payer=True,
    )

    proposal = code(telecom, setting)

    assert coded_lines(proposal.posting, proposal.budget) == [
        ("632005 41 01 110 000", "518 003", "321 000"),
        ("632003 41 09 111 000", "518 003", "321 000"),
    ]
    assert [line.amount for line in proposal.budget] == [Decimal("50.00"), Decimal("43.71")]
    assert proposal.needs_review
    assert "split per invoice entry into 2 lines" in proposal.review_reasons


def test_a_grant_funded_line_gets_its_transfer_and_goes_to_review(setting):
    tower = invoice(
        "grant",
        [("Lezecká veža – dodávka a montáž", "4980.00")],
        free_text=("Projekt podporený z dotácie BSK",),
    )

    proposal = code(tower, setting)

    assert proposal.budget[0].key == "633004 11H 06 200 000"
    assert proposal.budget[0].transfer == proposal.posting[0].transfer == "322002 11H 004"
    assert proposal.needs_review
    assert any("grant source" in reason for reason in proposal.review_reasons)


def test_a_missing_handwritten_number_takes_the_counters_next(setting):
    proposal = code(
        invoice("no-number", [("Výkon zodpovednej osoby", "30.75")], ico="50528041", number=None),
        setting,
    )

    assert proposal.document.number == "FD/223/26"
    assert proposal.confidence.document_number == 0.5
    assert proposal.needs_review


def test_a_missing_booking_date_stays_empty(setting):
    proposal = code(
        invoice("no-date", [("Výkon zodpovednej osoby", "30.75")], ico="50528041", booked=None),
        setting,
    )

    assert proposal.document.booking_date is None
    assert "the handwritten booking date was not read" in proposal.review_reasons


def test_a_number_already_used_is_a_warning(setting):
    proposal = code(
        invoice("used", [("Výkon zodpovednej osoby", "30.75")], ico="50528041", number="222"),
        setting,
    )

    assert proposal.validation.ok
    assert "FD/222/26 is already used" in proposal.validation.warnings
    assert proposal.needs_review


def test_vague_text_from_an_unknown_supplier_goes_to_review(setting):
    proposal = code(invoice("vague", [("Služby podľa objednávky č. 15", "240.00")]), setting)

    assert proposal.needs_review
    assert proposal.confidence.overall < 0.75
    assert proposal.validation.ok


def test_ocr_noise_goes_to_review(setting):
    mistyped = code(
        invoice(
            "mistyped",
            [("Mesačný paušálny poplatok", "35.00")],
            supplier="OZ Pomoc psíkom",
            ico="52823831",
            total="53.00",
        ),
        setting,
    )
    misread_ico = code(
        invoice(
            "misread-ico",
            [("Mesačný paušálny poplatok", "35.00")],
            supplier="OZ Pomoc psíkom",
            ico="52823832",
        ),
        setting,
    )

    assert "the entries add up to 35.00, the invoice total is 53.00" in mistyped.review_reasons
    assert "the supplier IČO '52823832' fails its check digit" in misread_ico.review_reasons
    assert misread_ico.supplier.known  # found by name
    assert misread_ico.budget[0].key == "637005 41 03 100 001"


def test_feedback_becomes_a_precedent_and_uses_up_the_number(setting):
    proposal = code(anchor("anchor-telekom").invoice, setting)
    feedback = Feedback(
        invoice_id=proposal.invoice_id,
        bundle_id=proposal.bundle_id,
        action="accepted",
        proposal=proposal,
        final=proposal.coding(),
    )

    memory, counters = apply_feedback(
        feedback, setting["memory"], setting["counters"], ReferenceIndex(setting["bundle"])
    )

    telekom = memory.find("35763469")
    assert telekom.precedents[0].document_number == "FD/144/26"
    assert telekom.precedents[0].variable_symbol == "8390051427"
    assert len(telekom.precedents) == 2
    assert "FD/144/26" in counters.used_numbers
    assert counters.last_used["FD/2026"] == 222  # 144 is below the counter

    again = code(anchor("anchor-telekom").invoice, setting, memory=memory, counters=counters)
    assert "FD/144/26 is already used" in again.validation.warnings
    assert any("already booked as FD/144/26" in w for w in again.validation.warnings)


def test_a_counter_number_moves_the_counter(setting):
    proposal = code(
        invoice("counted", [("Výkon zodpovednej osoby", "30.75")], ico="50528041", number=None),
        setting,
    )
    feedback = Feedback(
        invoice_id=proposal.invoice_id,
        bundle_id=proposal.bundle_id,
        action="accepted",
        proposal=proposal,
        final=proposal.coding(),
    )

    _, counters = apply_feedback(
        feedback, setting["memory"], setting["counters"], ReferenceIndex(setting["bundle"])
    )

    assert counters.last_used["FD/2026"] == 223
