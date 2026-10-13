"""S4, decision. In order: the supplier's newest compatible precedent wins outright; the canteen
food rule fixes its position; a single rule-consistent candidate wins; otherwise the best
rule-consistent candidate, or failing that the best one, is proposed for review with up to
fifteen ranked alternatives. An invoice is split only when its entries name different
buildings or activities, and a split always goes to review. The full version adds a
ranking model where this stage now asks for review."""

from decimal import Decimal

from riso.engine.models import (
    Candidate,
    CandidateSet,
    ChosenLine,
    Decision,
    NormalisedInvoice,
    ResolvedContext,
)
from riso.engine.s3_candidates import canteen_key, position_function
from riso.knowledge import STRONG, KnowledgeBase
from riso.reference import ReferenceIndex

MAX_ALTERNATIVES = 15
SINGLE_CANDIDATE_FLOOR = {3: 0.85, 2: 0.85, 1: 0.8}  # by tier


def decide(
    invoice: NormalisedInvoice,
    context: ResolvedContext,
    candidates: CandidateSet,
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
) -> Decision:
    ranked = candidates.invoice
    if invoice.gross is None:
        return Decision(
            rule="none",
            lines=(),
            alternatives=ranked[:MAX_ALTERNATIVES],
            reasons=("without the invoice total there is no amount to book",),
        )
    split = _split(invoice, candidates, index)
    if split is not None:
        return split

    # The newest compatible precedent: a correction the accountant just made outranks an
    # older habit, and an older precedent for the building the invoice names outranks a newer
    # one for another building.
    precedents = sorted(
        (c for c in ranked if c.precedent is not None), key=lambda c: c.precedent_rank or 0
    )
    compatible = next(
        (c for c in precedents if _compatible(c, invoice, ranked, index, knowledge)), None
    )
    if compatible is not None:
        return _one("precedent", compatible, invoice, ranked)
    if context.canteen_food:
        canteen = next((c for c in ranked if c.budget_key == canteen_key(knowledge)), None)
        if canteen is not None:
            return _one("canteen_rule", canteen, invoice, ranked)
    single = _single_consistent(ranked)
    if single is not None:
        # Being the only candidate that fits every rule is evidence in itself.
        floor = SINGLE_CANDIDATE_FLOOR.get(single.tier, 0.0)
        return _one(
            "single_candidate", single, invoice, ranked, confidence=max(single.score, floor)
        )
    if not ranked:
        return Decision(
            rule="none", lines=(), alternatives=(), reasons=("no budget position fits the invoice",)
        )
    reasons = []
    if precedents:
        reasons.append("the invoice names another activity than this supplier's earlier invoices")
    reasons.append(
        "several budget positions fit; the best is proposed"
        if len(ranked) > 1
        else "only one weak match"
    )
    best = next((c for c in ranked if c.consistent), ranked[0])
    return _one("best_candidate", best, invoice, ranked, tuple(reasons))


def _one(
    rule: str,
    chosen: Candidate,
    invoice: NormalisedInvoice,
    ranked: tuple[Candidate, ...],
    reasons: tuple[str, ...] = (),
    confidence: float | None = None,
) -> Decision:
    assert invoice.gross is not None
    line = ChosenLine(
        candidate=chosen,
        amount=invoice.gross,
        confidence=chosen.score if confidence is None else confidence,
    )
    return Decision(
        rule=rule,
        lines=(line,),
        alternatives=tuple(c for c in ranked if c.budget_key != chosen.budget_key)[
            :MAX_ALTERNATIVES
        ],
        reasons=reasons,
    )


def _compatible(
    precedent: Candidate,
    invoice: NormalisedInvoice,
    ranked: tuple[Candidate, ...],
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
) -> bool:
    """The invoice names no other building or activity than the precedent's position, it
    does not name another position outright (the Mother's Day refreshments from the
    supplier of the office's cleaning supplies), and its concepts, if any, include the
    precedent's economic code."""
    position = index.expense[precedent.budget_key]
    named = set(invoice.invoice_functions())
    if named and named != {position_function(position)}:
        return False
    if any(
        c.consistent and c.tier == 3 and index.expense[c.budget_key].ek != position.ek
        for c in ranked
    ):
        return False
    eks = {
        ek
        for name in invoice.concept_names()
        if knowledge.lexicon.concepts[name].weight >= STRONG
        for ek in knowledge.lexicon.concepts[name].ek
    }
    return not eks or position.ek in eks


def _single_consistent(ranked: tuple[Candidate, ...]) -> Candidate | None:
    """The one rule-consistent candidate in the best tier: a description that names what the
    invoice names beats one about the same concept, which beats a generic position."""
    consistent = [c for c in ranked if c.consistent]
    if not consistent:
        return None
    best_tier = max(c.tier for c in consistent)
    top = [c for c in consistent if c.tier == best_tier]
    return top[0] if len(top) == 1 else None


def _split(
    invoice: NormalisedInvoice, candidates: CandidateSet, index: ReferenceIndex
) -> Decision | None:
    """One line per entry, merging entries that land on the same position, when entries name
    different buildings or activities and every entry has an amount."""
    entries = invoice.document.lines
    choices = {
        i: chosen
        for i, line in enumerate(candidates.lines)
        if (chosen := next((c for c in line if c.consistent), None)) is not None
    }
    functions = {position_function(index.expense[c.budget_key]) for c in choices.values()}
    if len(entries) < 2 or len(functions) < 2:
        return None
    if any(amount is None for amount in invoice.line_amounts) or not candidates.invoice:
        return None
    grouped: dict[str, tuple[Candidate, Decimal, int]] = {}
    for i, amount in enumerate(invoice.line_amounts):
        assert amount is not None
        candidate = choices.get(i, candidates.invoice[0])
        kept = grouped.get(candidate.budget_key)
        grouped[candidate.budget_key] = (
            (candidate, amount, i) if kept is None else (kept[0], kept[1] + amount, kept[2])
        )
    lines = tuple(
        ChosenLine(candidate=c, amount=amount, confidence=c.score, invoice_line=i)
        for c, amount, i in grouped.values()
    )
    return Decision(
        rule="split",
        lines=lines,
        alternatives=candidates.invoice[:MAX_ALTERNATIVES],
        reasons=(f"split per invoice entry into {len(lines)} lines",),
    )
