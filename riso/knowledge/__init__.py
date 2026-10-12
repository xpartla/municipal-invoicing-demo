"""Engine knowledge authored for the demo (plan section 6): the EK to SU bridge, AU rules, the
function map, the transfer rule, the canteen food rule, the lexicon and the description style.
The YAML files live under knowledge/<budget year>/ in the repository and are loaded here."""

from pydantic import BaseModel


class KnowledgeBase(BaseModel):
    budget_year: int


def load_knowledge(budget_year: int) -> KnowledgeBase:
    raise NotImplementedError("The knowledge base is authored in M1")
