"""The Slovak wording of the engine's messages (P2-M4-T08). The engine speaks English in the
API; the frontend translates its messages with `frontend/src/i18n/sk/engine.json`, so every
message the engine produces must have a pattern there, or a Slovak page would show English.
Moved from `tests/test_web.py` with the catalogue."""

import json
import re
from decimal import Decimal

import pytest

from riso import paths
from riso.contracts import BudgetLine, Coding, DocumentRef, Feedback, PostingLine
from riso.dataset import load_cases
from riso.engine import code_invoice
from riso.engine.s6_validate import check_coding
from riso.engine.s8_feedback import apply_feedback
from riso.eval.files import initial_counters, initial_memory
from riso.knowledge import knowledge_for
from riso.reference import ReferenceIndex

BOLDOG = "00305863"
CATALOGUE_FILE = paths.REPO_ROOT / "frontend" / "src" / "i18n" / "sk" / "engine.json"
CATALOGUE = json.loads(CATALOGUE_FILE.read_text(encoding="utf-8"))
PATTERNS = [re.compile(pattern) for pattern, _ in CATALOGUE["messages"]]


def covered(message: str) -> bool:
    return any(pattern.search(message) for pattern in PATTERNS)


def _messages(proposal) -> list[str]:
    return [
        *proposal.review_reasons,
        *proposal.validation.errors,
        *proposal.validation.warnings,
        *(item.detail for item in proposal.evidence),
        *(alternative.why for alternative in proposal.alternatives),
    ]


def test_every_message_the_dataset_produces_has_slovak_wording(source, tmp_path):
    setting = {
        "entity": source.context(BOLDOG),
        "bundle": source.bundle(BOLDOG),
        "knowledge": knowledge_for(BOLDOG, 2026),
        "memory": initial_memory(BOLDOG),
        "counters": initial_counters(BOLDOG),
    }
    index = ReferenceIndex(setting["bundle"])
    messages = set()
    for case in load_cases():
        proposal = code_invoice(case.invoice, **setting)
        messages.update(_messages(proposal))
        if proposal.budget:
            # Accepted, then coded again: the number is used and the invoice already booked.
            feedback = Feedback(
                invoice_id=proposal.invoice_id,
                bundle_id=proposal.bundle_id,
                action="accepted",
                proposal=proposal,
                final=proposal.coding(),
            )
            memory, counters = apply_feedback(
                feedback, setting["memory"], setting["counters"], index
            )
            again = code_invoice(case.invoice, **setting | {"memory": memory, "counters": counters})
            messages.update(_messages(again))
    messages.update(warning.message for warning in setting["bundle"].warnings)

    assert sorted(m for m in messages if not covered(m)) == []
    assert any("is already used" in m for m in messages)  # the second pass did its job


def _broken(**changes) -> Coding:
    line = {"md": "518 003", "dal": "321 000", "key": "632005 41 01 110 000"} | changes
    ek, zdroj, oddiel, trieda, analytika = line["key"].split(" ")
    return Coding(
        document=DocumentRef(
            series=changes.get("series", "FD"), number=changes.get("number", "FD/144/26")
        ),
        posting=[PostingLine(md=line["md"], dal=line["dal"], amount=Decimal("10.00"), text="x")],
        budget=[
            BudgetLine(
                key=line["key"],
                ek=ek,
                zdroj=zdroj,
                oddiel=oddiel,
                trieda=trieda,
                analytika=analytika,
                amount=Decimal("10.00"),
                text="x",
                transfer=changes.get("transfer"),
            )
        ],
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"md": "518 999"},
        {"dal": "379 000"},
        {"key": "632005 41 01 110 999"},
        {"md": "321 000"},
        {"key": "717001 41 01 110 001", "md": "518 001"},
        {"series": "XY"},
        {"number": "FD/44/26"},
        {"transfer": "999 99 999"},
    ],
)
def test_validation_errors_have_slovak_wording(index, changes):
    errors = check_coding(_broken(**changes), index, gross=Decimal("99.00")).errors

    assert errors
    assert [e for e in errors if not covered(e)] == []


def test_the_catalogue_names_every_concept_function_and_check(index):
    knowledge = knowledge_for(BOLDOG, 2026)

    assert set(knowledge.lexicon.concepts) <= set(CATALOGUE["concepts"])
    assert {f.function for f in knowledge.functions.functions} <= set(CATALOGUE["functions"])
    validation = check_coding(_broken(), index)
    assert set(validation.checks) <= set(CATALOGUE["checks"])
