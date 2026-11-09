"""A customer without conventions (phase 2 plan §6.4): with Boldog's lists but none of its
rules, every dataset invoice gets a valid proposal or a review, never a validation failure
for a missing analytic account. And the fallback itself: a missing AU falls back to the SU's
000, then to its only AU, otherwise the line goes to review."""

import json
import re

import pytest

from riso import paths
from riso.contracts import Counters, SupplierMemory
from riso.dataset import load_cases
from riso.engine import code_invoice
from riso.knowledge import Conventions, knowledge_for, load_knowledge, merge
from riso.reference import LocalReferenceSource

BOLDOG = "00305863"


@pytest.fixture(scope="module")
def source():
    return LocalReferenceSource()


ENGINE_MESSAGES = paths.REPO_ROOT / "frontend" / "src" / "i18n" / "sk" / "engine.json"


def _code(case, source, *, knowledge, bundle=None):
    return code_invoice(
        case.invoice,
        entity=source.context(BOLDOG),
        bundle=bundle or source.bundle(BOLDOG),
        memory=SupplierMemory(entity_ico=BOLDOG),
        counters=Counters(entity_ico=BOLDOG, last_used={}),
        knowledge=knowledge,
    )


def _cases(*splits):
    return [c for c in load_cases() if c.split in splits]


def test_without_conventions_every_invoice_is_valid_or_reviewed(source):
    knowledge = load_knowledge(2026)  # the global knowledge alone
    coded = 0
    for case in _cases("anchor", "seed"):
        proposal = _code(case, source, knowledge=knowledge)
        assert proposal.validation.errors == [], (case.id, proposal.validation.errors)
        assert not any("analytic account" in r for r in proposal.review_reasons), case.id
        coded += bool(proposal.posting)
    assert coded >= 20  # most of them still get a coding


def test_without_conventions_the_debit_takes_the_sus_000(source):
    telekom = next(c for c in load_cases() if c.id == "anchor-telekom")
    with_rules = _code(telekom, source, knowledge=knowledge_for(BOLDOG, 2026))
    without = _code(telekom, source, knowledge=load_knowledge(2026))
    assert with_rules.posting[0].md == "518 003"  # Boldog's telecom rule
    assert without.posting[0].md == "518 000"


def _without_accounts(bundle, *keys):
    return bundle.model_copy(update={"accounts": [a for a in bundle.accounts if a.key not in keys]})


def test_a_rule_naming_a_missing_au_falls_back_to_000(source):
    telekom = next(c for c in load_cases() if c.id == "anchor-telekom")
    bundle = _without_accounts(source.bundle(BOLDOG), "518 003")
    proposal = _code(telekom, source, knowledge=knowledge_for(BOLDOG, 2026), bundle=bundle)
    assert proposal.posting[0].md == "518 000"
    assert proposal.validation.errors == []
    assert not any("analytic account" in r for r in proposal.review_reasons)


def test_without_000_the_only_au_is_taken(source):
    telekom = next(c for c in load_cases() if c.id == "anchor-telekom")
    only = [a.key for a in source.bundle(BOLDOG).accounts if a.su == "518" and a.au != "001"]
    bundle = _without_accounts(source.bundle(BOLDOG), *only)
    proposal = _code(telekom, source, knowledge=load_knowledge(2026), bundle=bundle)
    assert proposal.posting[0].md == "518 001"
    assert not any("analytic account" in r for r in proposal.review_reasons)


def test_without_000_and_with_several_aus_the_line_goes_to_review(source):
    telekom = next(c for c in load_cases() if c.id == "anchor-telekom")
    bundle = _without_accounts(source.bundle(BOLDOG), "518 000")
    proposal = _code(telekom, source, knowledge=load_knowledge(2026), bundle=bundle)
    assert proposal.needs_review
    reason = next(r for r in proposal.review_reasons if r.startswith("no analytic account"))
    md = proposal.posting[0].md
    assert reason == f"no analytic account: 518 000 is not in the chart, {md} is a guess"
    assert md.startswith("518 ") and proposal.validation.errors == []
    assert proposal.confidence.md <= 0.5
    catalogue = json.loads(ENGINE_MESSAGES.read_text(encoding="utf-8"))
    assert any(re.match(pattern, reason) for pattern, _ in catalogue["messages"])


def test_boldogs_conventions_merged_from_an_empty_set_change_nothing():
    assert merge(load_knowledge(2026), Conventions()) == load_knowledge(2026)
