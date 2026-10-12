"""S4, decision: a precedent with a compatible description wins outright, then a single
rule-consistent candidate. Otherwise the best candidate is proposed for review with up to about
fifteen ranked alternatives. Also decides the per-entry split. The full version adds a ranking
model at this point."""

from riso.engine.models import Candidate, Decision, NormalisedInvoice, ResolvedContext


def decide(
    invoice: NormalisedInvoice, context: ResolvedContext, candidates: list[Candidate]
) -> Decision:
    raise NotImplementedError("S4, decision, is built in M1")
