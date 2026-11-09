"""Engine knowledge (plan section 6): the EK to SU bridge, the function map, the lexicon, the
transfer rule and the description style, read from knowledge/<budget year>/ and versioned by
year, because the economic classification changes each January.

A customer's own rules (AU rules, the canteen rule, local concepts) are its conventions
(phase 2 plan §6.4): committed per customer and year as data/conventions/<IČO>/<year>.yaml
for the file-based tools, and kept in the database for the app. `merge` combines the two;
`knowledge_for` does it for a committed customer."""

from functools import lru_cache
from pathlib import Path

import yaml

from riso import paths
from riso.knowledge.model import STRONG, Concept, Conventions, KnowledgeBase, merge

FILES = {
    "bridge": "ek_su_bridge.yaml",
    "functions": "cofog_map.yaml",
    "lexicon": "lexicon.yaml",
    "transfer_rules": "transfer_rules.yaml",
    "style": "style.yaml",
}


class UnknownKnowledge(LookupError):
    pass


@lru_cache(maxsize=8)
def load_knowledge(budget_year: int, root: Path = paths.KNOWLEDGE_DIR) -> KnowledgeBase:
    """The global knowledge of one budget year, without any customer's conventions. Loaded
    once per process; treat it as read-only."""
    directory = root / str(budget_year)
    if not directory.is_dir():
        raise UnknownKnowledge(f"no knowledge base for budget year {budget_year} in {root}")
    content = {
        field: yaml.safe_load((directory / name).read_text(encoding="utf-8"))
        for field, name in FILES.items()
    }
    return KnowledgeBase(budget_year=budget_year, **content)


def read_conventions(text: str) -> Conventions:
    return Conventions.model_validate(yaml.safe_load(text) or {})


@lru_cache(maxsize=32)
def load_conventions(ico: str, budget_year: int, root: Path = paths.CONVENTIONS_DIR) -> Conventions:
    """A customer's committed conventions for the year; empty when it has none."""
    path = root / ico / f"{budget_year}.yaml"
    if not path.is_file():
        return Conventions()
    return read_conventions(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=32)
def knowledge_for(
    ico: str,
    budget_year: int,
    root: Path = paths.KNOWLEDGE_DIR,
    conventions_root: Path = paths.CONVENTIONS_DIR,
) -> KnowledgeBase:
    """The global knowledge of the year merged with the customer's committed conventions."""
    return merge(
        load_knowledge(budget_year, root), load_conventions(ico, budget_year, conventions_root)
    )


__all__ = [
    "STRONG",
    "Concept",
    "Conventions",
    "KnowledgeBase",
    "UnknownKnowledge",
    "knowledge_for",
    "load_conventions",
    "load_knowledge",
    "merge",
    "read_conventions",
]
