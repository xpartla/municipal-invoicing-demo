"""The knowledge base as authored in knowledge/<budget year>/*.yaml (plan section 6)."""

from functools import cached_property
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from riso.contracts.base import AccountKey, Analytika, Au, Ek, Su, Zdroj
from riso.knowledge.terms import TermIndex
from riso.text import cased_words, fold, words

FunctionCode = Annotated[str, StringConstraints(pattern=r"^\d{2} \d{3}$")]
EkPrefix = Annotated[str, StringConstraints(pattern=r"^\d{1,6}$")]

# Concepts at or above this weight are evidence; below it they only add alternatives.
STRONG = 0.5


class Authored(BaseModel):
    """Base of the authored files: unknown keys are rejected, so a typo fails loudly."""

    model_config = ConfigDict(extra="forbid")


class BridgeRule(Authored):
    ek: EkPrefix
    su: Su
    note: str | None = None


class AuRule(Authored):
    """Holds when every condition given holds; each list matches any of its items."""

    au: Au
    concepts: list[str] = Field(default_factory=list)
    function: list[FunctionCode] = Field(default_factory=list)
    ek: list[EkPrefix] = Field(default_factory=list)
    zdroj: list[Zdroj] = Field(default_factory=list)
    terms: list[str] = Field(
        default_factory=list, description="In the invoice or the budget position's description"
    )
    note: str | None = None

    @cached_property
    def term_index(self) -> TermIndex:
        return TermIndex((term, "term") for term in self.terms)


class AccountRules(Authored):
    default: Au
    rules: list[AuRule] = Field(default_factory=list)


class AuRules(Authored):
    debit: dict[Su, AccountRules]
    credit: dict[Su, AccountRules]


class FunctionEntry(Authored):
    function: FunctionCode
    name: str
    terms: list[str] = Field(default_factory=list)
    abbreviations: list[str] = Field(default_factory=list)


class FunctionMap(Authored):
    default: FunctionCode
    functions: list[FunctionEntry]


class Concept(Authored):
    terms: list[str] = Field(min_length=1)
    ek: list[Ek] = Field(default_factory=list, description="Most likely first")
    weight: float = Field(default=1.0, gt=0, le=1)
    text: str | None = Field(default=None, description="Posting text in the accountant's style")


class Lexicon(Authored):
    stopwords: list[str]
    credit_note_markers: list[str]
    concepts: dict[str, Concept]


class TransferRules(Authored):
    zdroj_prefixes: list[str]
    from_income_grants: bool
    never: list[Zdroj]


class CanteenRule(Authored):
    """Series and supplier account come from the entity settings."""

    concepts: list[str]
    function: FunctionCode
    zdroj: Zdroj
    ek: Ek
    analytika: Analytika
    alternatives: list[Analytika] = Field(default_factory=list)
    md: AccountKey


class Style(Authored):
    max_length: int = Field(ge=10)
    month_for: list[str] = Field(
        default_factory=list, description="Concepts whose posting text gets the month of service"
    )


class KnowledgeBase(Authored):
    budget_year: int
    bridge: list[BridgeRule]
    au_rules: AuRules
    functions: FunctionMap
    lexicon: Lexicon
    transfer_rules: TransferRules
    canteen: CanteenRule
    style: Style

    @model_validator(mode="after")
    def _known_concepts(self) -> "KnowledgeBase":
        known = set(self.lexicon.concepts)
        used = (
            set(self.canteen.concepts)
            | set(self.style.month_for)
            | {
                concept
                for table in (self.au_rules.debit, self.au_rules.credit)
                for rules in table.values()
                for rule in rules.rules
                for concept in rule.concepts
            }
        )
        if used - known:
            raise ValueError(f"concepts used but not in the lexicon: {sorted(used - known)}")
        return self

    @cached_property
    def concept_terms(self) -> TermIndex:
        return TermIndex(
            (term, name)
            for name, concept in self.lexicon.concepts.items()
            for term in concept.terms
        )

    @cached_property
    def function_terms(self) -> TermIndex:
        return TermIndex(
            (term, entry.function) for entry in self.functions.functions for term in entry.terms
        )

    @cached_property
    def abbreviations(self) -> dict[str, str]:
        """Abbreviation, case kept and diacritics folded, to function code."""
        return {
            fold(abbreviation): entry.function
            for entry in self.functions.functions
            for abbreviation in entry.abbreviations
        }

    @cached_property
    def credit_note_terms(self) -> TermIndex:
        return TermIndex((term, "credit_note") for term in self.lexicon.credit_note_markers)

    @cached_property
    def stopwords(self) -> frozenset[str]:
        return frozenset(self.lexicon.stopwords)

    @cached_property
    def remembered_concepts(self) -> dict[tuple[str, ...], frozenset[str]]:
        return {}

    def concepts_in(self, tokens: tuple[str, ...]) -> frozenset[str]:
        """Concepts whose terms occur in the words. Remembered, because the same budget
        descriptions are matched for every invoice."""
        found = self.remembered_concepts.get(tokens)
        if found is None:
            found = frozenset(meaning for _, meaning in self.concept_terms.search(tokens))
            self.remembered_concepts[tokens] = found
        return found

    @cached_property
    def remembered_functions(self) -> dict[str, frozenset[str]]:
        return {}

    def functions_in(self, text: str) -> frozenset[str]:
        """Function codes a text names, by word or by abbreviation: 'MŠ - elekt.energia'
        names the kindergarten. Remembered, like concepts_in."""
        found = self.remembered_functions.get(text)
        if found is None:
            found = frozenset(meaning for _, meaning in self.function_terms.search(words(text)))
            found |= {self.abbreviations[w] for w in cased_words(text) if w in self.abbreviations}
            self.remembered_functions[text] = found
        return found

    def is_strong(self, concept: str) -> bool:
        return self.lexicon.concepts[concept].weight >= STRONG

    def su_for(self, ek: str) -> BridgeRule | None:
        """The bridge rule with the longest EK prefix matching the code."""
        matching = [rule for rule in self.bridge if ek.startswith(rule.ek)]
        return max(matching, key=lambda rule: len(rule.ek), default=None)

    def expects_transfer(self, zdroj: str, grant_sources: frozenset[str]) -> bool:
        """Whether a budget line with this zdroj needs a transfer (transfer_rules.yaml);
        grant_sources are the zdroj codes on the income side's grant rows."""
        rules = self.transfer_rules
        if zdroj in rules.never:
            return False
        if any(zdroj.startswith(prefix) for prefix in rules.zdroj_prefixes):
            return True
        return rules.from_income_grants and zdroj in grant_sources
