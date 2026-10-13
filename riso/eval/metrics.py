"""Scoring: one proposal against its case (CaseResult), and the metrics of plan section 9 over
a set of case results."""

from collections.abc import Callable, Iterable

from riso.contracts import (
    BudgetLine,
    CaseResult,
    CodingProposal,
    DatasetCase,
    LineCodes,
    PostingLine,
    Rate,
)

# Each field of a line as the accountant types it; COFOG is oddiel and trieda together.
FIELDS: dict[str, Callable[[LineCodes], str]] = {
    "ek": lambda line: line.key.split(" ")[0],
    "zdroj": lambda line: line.key.split(" ")[1],
    "cofog": lambda line: " ".join(line.key.split(" ")[2:4]),
    "analytika": lambda line: line.key.split(" ")[4],
    "md": lambda line: line.md,
    "dal": lambda line: line.dal,
}

# Metrics repeated per supplier group and per tag.
GROUP_METRICS = ("correct", "full_key", "ek", "md", "review_rate", "silent_errors")


def score_case(case: DatasetCase, proposal: CodingProposal, *, known: bool) -> CaseResult:
    expected = case.expected
    proposed = _line_codes(proposal.posting, proposal.budget)
    alternatives = [alternative.budget_key for alternative in proposal.alternatives]
    common = {
        "case_id": case.id,
        "tags": case.tags,
        "supplier": case.invoice.supplier.name,
        "known_supplier": known,
        "expected_outcome": expected.outcome,
        "proposed": proposed,
        "alternatives": alternatives,
        "validation_ok": proposal.validation.ok if proposal.budget else None,
        "needs_review": proposal.needs_review,
        "expected_review": expected.needs_review,
        "review_reasons": proposal.review_reasons,
        "confidence": proposal.confidence.overall,
    }
    coding = expected.coding
    if coding is None:
        return CaseResult(**common, correct=not proposed, full_key=None)

    want = _line_codes(coding.posting, coding.budget)
    got = _aligned(coding.budget, proposal.budget, proposed)
    same_count = len(want) == len(proposed)
    fields = {
        name: same_count and all(field(w) == field(g) for w, g in zip(want, got, strict=True))
        for name, field in FIELDS.items()
    }
    full_key = same_count and all(w.key == g.key for w, g in zip(want, got, strict=True))
    lines_ok = same_count and want == got
    top3 = None
    if len(want) == 1:
        offered = [line.key for line in proposed[:1]] + alternatives
        top3 = want[0].key in offered[:3]
    document = coding.document
    number_ok = None if document.number is None else proposal.document.number == document.number
    date_ok = (
        None
        if document.booking_date is None
        else proposal.document.booking_date == document.booking_date
    )
    return CaseResult(
        **common,
        expected=want,
        correct=lines_ok and number_ok is not False and date_ok is not False,
        full_key=full_key,
        fields=fields,
        top3=top3,
        split_ok=same_count,
        number_ok=number_ok,
        date_ok=date_ok,
    )


def metrics(results: list[CaseResult]) -> dict[str, Rate]:
    coded = [r for r in results if r.expected_outcome == "coded"]
    flagged = [r for r in results if r.needs_review]
    wrong = [r for r in results if not r.correct]
    return {
        "correct": _rate(results, lambda r: r.correct),
        "full_key": _rate(coded, lambda r: r.full_key is True),
        "full_line": _rate(coded, _lines_ok),
        **{name: _rate(coded, lambda r, name=name: r.fields[name]) for name in FIELDS},
        "top3": _rate([r for r in coded if r.top3 is not None], lambda r: r.top3 is True),
        "split": _rate(coded, lambda r: r.split_ok is True),
        "manual_entry": _rate(
            [r for r in results if r.expected_outcome == "manual_entry"], lambda r: r.correct
        ),
        "validation": _rate(
            [r for r in results if r.validation_ok is not None], lambda r: r.validation_ok is True
        ),
        "document_number": _rate(
            [r for r in coded if r.number_ok is not None], lambda r: r.number_ok is True
        ),
        "booking_date": _rate(
            [r for r in coded if r.date_ok is not None], lambda r: r.date_ok is True
        ),
        "review_rate": _rate(results, lambda r: r.needs_review),
        "review_precision": _rate(flagged, lambda r: not r.correct),
        "review_recall": _rate(wrong, lambda r: r.needs_review),
        "silent_errors": _rate(results, lambda r: not r.correct and not r.needs_review),
        "expected_review": _rate(
            [r for r in results if r.expected_review is not None],
            lambda r: r.needs_review == r.expected_review,
        ),
    }


def group_metrics(results: list[CaseResult]) -> dict[str, Rate]:
    found = metrics(results)
    return {name: found[name] for name in GROUP_METRICS}


def by_supplier(results: list[CaseResult]) -> dict[str, dict[str, Rate]]:
    groups = {
        "known": [r for r in results if r.known_supplier],
        "new": [r for r in results if not r.known_supplier],
    }
    return {name: group_metrics(group) for name, group in groups.items() if group}


def by_tag(results: list[CaseResult], tags: Iterable[str]) -> dict[str, dict[str, Rate]]:
    found = {}
    for tag in tags:
        group = [r for r in results if tag in r.tags]
        if group:
            found[tag] = group_metrics(group)
    return found


def _rate(results: list[CaseResult], hit: Callable[[CaseResult], bool]) -> Rate:
    hits = sum(1 for r in results if hit(r))
    return Rate(hits=hits, n=len(results), value=round(hits / len(results), 4) if results else None)


def _lines_ok(result: CaseResult) -> bool:
    """Every line's key, MD and DAL match, whatever the document header."""
    return result.full_key is True and all(result.fields.get(name) for name in ("md", "dal"))


def _line_codes(posting: list[PostingLine], budget: list[BudgetLine]) -> list[LineCodes]:
    return [LineCodes(key=b.key, md=p.md, dal=p.dal) for p, b in zip(posting, budget, strict=False)]


def _aligned(
    expected: list[BudgetLine], proposed: list[BudgetLine], codes: list[LineCodes]
) -> list[LineCodes]:
    """The proposed lines in the order of the expected ones, so that a split whose lines come
    in another order still compares line by line: paired by amount, then by key, then in
    order. Lines are compared only when both have as many."""
    if len(expected) != len(proposed):
        return codes
    unused = list(range(len(proposed)))
    order = []
    for line in expected:
        pick = next((i for i in unused if proposed[i].amount == line.amount), None)
        if pick is None:
            pick = next((i for i in unused if proposed[i].key == line.key), unused[0])
        unused.remove(pick)
        order.append(pick)
    return [codes[i] for i in order]
