import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from riso import paths
from riso.contracts import (
    BudgetLine,
    CodingProposal,
    DatasetCase,
    Feedback,
    OcrMeta,
    PostingLine,
)
from riso.contracts.schemas import stale_schemas
from riso.engine.s6_validate import check_coding

EXAMPLE = Path(__file__).parent / "fixtures" / "coding-proposal-example.json"


def _example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_the_exported_schemas_match_the_models():
    assert stale_schemas(paths.SCHEMAS_DIR) == [], "run `riso export-schemas`"


def test_the_plans_example_proposal_is_valid_and_resolves(index):
    proposal = CodingProposal.model_validate(_example())

    assert check_coding(proposal.coding(), index, gross=proposal.invoice.gross).ok


def test_amounts_are_exact_decimals_and_json_numbers():
    line = PostingLine.model_validate(
        {"md": "518 003", "dal": "321 000", "amount": 93.71, "text": "tel.poplatky"}
    )

    assert line.amount == Decimal("93.71")
    assert json.loads(line.model_dump_json())["amount"] == 93.71


def test_booking_amounts_have_at_most_two_decimals():
    with pytest.raises(ValidationError, match="decimal places"):
        PostingLine(md="518 003", dal="321 000", amount=Decimal("83.707"), text="x")


def test_a_budget_key_must_agree_with_its_parts():
    line = _example()["budget"][0]

    with pytest.raises(ValidationError, match="does not match its parts"):
        BudgetLine.model_validate({**line, "ek": "632003"})


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CodingProposal.model_validate({**_example(), "needs_reveiw": True})


def test_ocr_confidence_is_keyed_by_known_paths():
    assert OcrMeta(confidence={"handwritten.date": 0.8, "lines[0].gross": 1.0})
    with pytest.raises(ValidationError, match="unknown field path"):
        OcrMeta(confidence={"handwriting.date": 0.8})
    with pytest.raises(ValidationError, match="between 0 and 1"):
        OcrMeta(confidence={"totals.gross": 1.5})


def test_accepted_feedback_keeps_the_proposed_coding():
    proposal = CodingProposal.model_validate(_example())
    corrected = proposal.coding().model_copy(deep=True)
    corrected.posting[0].text = "telefón jún"
    common = {"invoice_id": "anchor-telekom", "bundle_id": "00305863/2026-08"}

    Feedback(**common, action="accepted", proposal=proposal, final=proposal.coding())
    Feedback(**common, action="corrected", proposal=proposal, final=corrected)
    with pytest.raises(ValidationError, match="use 'corrected'"):
        Feedback(**common, action="accepted", proposal=proposal, final=corrected)


def test_a_coded_case_has_a_coding_and_a_manual_entry_has_none():
    case = json.loads(
        (paths.INVOICES_DIR / "anchor" / "anchor-telekom.json").read_text(encoding="utf-8")
    )
    coding = case["expected"]["coding"]

    DatasetCase.model_validate({**case, "expected": {"outcome": "manual_entry"}})
    with pytest.raises(ValidationError, match="a coded outcome has a coding"):
        DatasetCase.model_validate(
            {**case, "expected": {"outcome": "manual_entry", "coding": coding}}
        )
    with pytest.raises(ValidationError, match="a coded outcome has a coding"):
        DatasetCase.model_validate({**case, "expected": {"outcome": "coded"}})
