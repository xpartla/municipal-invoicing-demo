"""Evaluation against the dataset's expected outcomes (plan section 9). M1 compares one
proposal with its case; the metrics over the held-out set come in M2."""

from riso.contracts import CodingProposal, DatasetCase


def coded_lines(posting, budget) -> list[tuple[str, str, str]]:
    """(budget key, MD, DAL) per line: what the accountant types into the software."""
    return [(b.key, p.md, p.dal) for p, b in zip(posting, budget, strict=False)]


def compare(proposal: CodingProposal, case: DatasetCase) -> str | None:
    """None when the proposal codes the case as expected, else what was expected."""
    expected = case.expected
    if expected.outcome == "manual_entry" or expected.coding is None:
        return None if not proposal.budget else "manual entry"
    want = coded_lines(expected.coding.posting, expected.coding.budget)
    got = coded_lines(proposal.posting, proposal.budget)
    return None if got == want else "; ".join(" ".join(line) for line in want)


def evaluate(cases: list[DatasetCase]) -> dict[str, float]:
    raise NotImplementedError("The metrics over the held-out set are built in M2")
