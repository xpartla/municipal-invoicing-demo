"""S7, explanation: evidence and confidence per field. Sets needs_review when a field is below
the threshold, a warning was raised or validation failed."""

from riso.contracts import Coding, CodingProposal, Validation
from riso.engine.models import Decision, NormalisedInvoice, ResolvedContext


def explain(
    invoice: NormalisedInvoice,
    context: ResolvedContext,
    decision: Decision,
    coding: Coding,
    validation: Validation,
) -> CodingProposal:
    raise NotImplementedError("S7, explanation, is built in M1")


def manual_entry(
    invoice: NormalisedInvoice, context: ResolvedContext, reason: str
) -> CodingProposal:
    """A proposal without lines, for invoices the accountant enters by hand, such as credit
    notes."""
    raise NotImplementedError("S7, explanation, is built in M1")
