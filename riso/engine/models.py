"""Intermediate structures passed between the pipeline stages (plan section 5)."""

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from riso.contracts import (
    Coding,
    EntityContext,
    Evidence,
    InvoiceDocument,
    PrecedentLine,
    SupplierRecord,
)


class StageResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourcedText(StageResult):
    """One piece of the invoice's text and where it came from."""

    source: str  # 'supplier.name', 'lines[0].description', 'free_text[1]'
    words: tuple[str, ...]
    cased_words: tuple[str, ...]


class Hit(StageResult):
    """A term of the knowledge base found in the invoice."""

    meaning: str  # a concept name or a function code
    term: str
    source: str


class NormalisedInvoice(StageResult):
    """S1: the invoice with derived values, its words, and what the knowledge base finds in
    them."""

    document: InvoiceDocument
    supplier_ico: str | None
    customer_ico: str | None
    gross: Decimal | None
    line_amounts: tuple[Decimal | None, ...]
    vat_payer: bool | None
    booking_date: dt.date | None
    handwritten_number: int | None
    service_period: tuple[int, int] | None  # (year, month)
    is_credit_note: bool
    texts: tuple[SourcedText, ...]
    concepts: tuple[Hit, ...]
    functions: tuple[Hit, ...]
    issues: tuple[str, ...]
    low_confidence: tuple[str, ...]

    def concept_names(self, source: str | None = None) -> frozenset[str]:
        return frozenset(h.meaning for h in self.concepts if source in (None, h.source))

    def named_functions(self, source: str | None = None) -> tuple[str, ...]:
        """Function codes the text names, most often named first."""
        hits = [h.meaning for h in self.functions if source in (None, h.source)]
        return tuple(sorted(dict.fromkeys(hits), key=lambda f: -hits.count(f)))

    def invoice_functions(self) -> tuple[str, ...]:
        """Function codes named for the invoice as a whole: anywhere outside the entries, or
        in at least half of them. Bin bags among cleaning supplies do not make the invoice
        one about waste management."""
        entries = len(self.document.lines)
        named = []
        for function in self.named_functions():
            sources = {h.source for h in self.functions if h.meaning == function}
            in_entries = {s for s in sources if s.startswith("lines[")}
            if sources - in_entries or 2 * len(in_entries) >= entries:
                named.append(function)
        return tuple(named)

    def all_words(self) -> tuple[str, ...]:
        return tuple(word for text in self.texts for word in text.words)


class ResolvedContext(StageResult):
    """S2: whose dictionaries apply, what is known about the supplier, and the header."""

    entity: EntityContext
    bundle_id: str
    supplier: SupplierRecord | None
    series: str
    canteen: bool
    canteen_food: bool
    zdroj: str  # the source an own-funded line gets
    document_number: str
    number_source: Literal["handwritten", "counter"]
    booking_date: dt.date | None
    used_numbers: frozenset[str]
    issues: tuple[str, ...]


class Candidate(StageResult):
    """S3: one budget position and what speaks for it."""

    budget_key: str
    score: float
    sources: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    consistent: bool = False  # fits the rules: concept EK, function, zdroj, analytika
    tier: int = 0  # 2: its description names what the invoice names; 1: same concept
    precedent: PrecedentLine | None = None
    precedent_number: str | None = None
    precedent_rank: int | None = None  # 0 for the supplier's newest precedent


class CandidateSet(StageResult):
    invoice: tuple[Candidate, ...]  # best first
    lines: tuple[tuple[Candidate, ...], ...]  # per entry that names its own function or concept
    function: str
    function_explicit: bool
    function_evidence: Evidence


class ChosenLine(StageResult):
    candidate: Candidate
    amount: Decimal
    confidence: float
    invoice_line: int | None = None


class Decision(StageResult):
    """S4: the budget line or lines to propose, the alternatives, and why to review."""

    rule: Literal[
        "precedent", "canteen_rule", "single_candidate", "best_candidate", "split", "none"
    ]
    lines: tuple[ChosenLine, ...]
    alternatives: tuple[Candidate, ...]
    reasons: tuple[str, ...]


class Derivation(StageResult):
    """S5: the complete coding, and how its accounts were found."""

    coding: Coding
    evidence: tuple[Evidence, ...]
    md_confidence: float
    dal_confidence: float
