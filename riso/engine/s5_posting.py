"""S5, posting derivation: EK to SU through the bridge, AU by the rules and precedent, the
credit 321 with its AU by series and project, amounts, and descriptions in the accountant's
short style. Returns the complete coding: the header from S2, the budget lines chosen in S4 and
one posting line for each."""

from riso.contracts import Coding
from riso.engine.models import Decision, NormalisedInvoice, ResolvedContext
from riso.knowledge import KnowledgeBase
from riso.reference import ReferenceIndex


def derive_coding(
    invoice: NormalisedInvoice,
    context: ResolvedContext,
    decision: Decision,
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
) -> Coding:
    raise NotImplementedError("S5, posting derivation, is built in M1")
