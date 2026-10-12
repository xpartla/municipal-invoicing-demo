"""Engine knowledge authored for the demo (plan section 6): the EK to SU bridge, AU rules, the
function map, the lexicon, the transfer rule, the canteen food rule and the description
style. Read from knowledge/<budget year>/ and versioned by year, because the economic
classification changes each January."""

from functools import lru_cache
from pathlib import Path

import yaml

from riso import paths
from riso.knowledge.model import STRONG, Concept, KnowledgeBase

FILES = {
    "bridge": "ek_su_bridge.yaml",
    "au_rules": "au_rules.yaml",
    "functions": "cofog_map.yaml",
    "lexicon": "lexicon.yaml",
    "transfer_rules": "transfer_rules.yaml",
    "canteen": "canteen.yaml",
    "style": "style.yaml",
}


class UnknownKnowledge(LookupError):
    pass


@lru_cache(maxsize=8)
def load_knowledge(budget_year: int, root: Path = paths.KNOWLEDGE_DIR) -> KnowledgeBase:
    """The knowledge base of one budget year. Loaded once per process; treat it as read-only."""
    directory = root / str(budget_year)
    if not directory.is_dir():
        raise UnknownKnowledge(f"no knowledge base for budget year {budget_year} in {root}")
    content = {
        field: yaml.safe_load((directory / name).read_text(encoding="utf-8"))
        for field, name in FILES.items()
    }
    return KnowledgeBase(budget_year=budget_year, **content)


__all__ = ["STRONG", "Concept", "KnowledgeBase", "UnknownKnowledge", "load_knowledge"]
