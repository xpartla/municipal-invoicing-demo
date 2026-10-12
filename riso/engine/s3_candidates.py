"""S3, candidate generation: supplier precedent, lexicon and rule matches for EK, function and
source, and lexical similarity between the invoice text and the budget-position descriptions,
merged with their provenance."""

from riso.engine.models import Candidate, NormalisedInvoice, ResolvedContext
from riso.knowledge import KnowledgeBase
from riso.reference import ReferenceIndex


def generate_candidates(
    invoice: NormalisedInvoice,
    context: ResolvedContext,
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
) -> list[Candidate]:
    raise NotImplementedError("S3, candidate generation, is built in M1")
