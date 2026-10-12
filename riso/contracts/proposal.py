"""CodingProposal, what the engine returns for one invoice (plan section 4), and Coding, its
core: the part the accountant types into the software, shared with ground truth and feedback."""

import datetime as dt
from typing import Literal

from pydantic import Field, model_validator

from riso.contracts.base import (
    AccountKey,
    Amount,
    Analytika,
    BookingAmount,
    BudgetKey,
    Contract,
    Ek,
    Ico,
    Oddiel,
    Trieda,
    Zdroj,
)
from riso.contracts.invoice import InvoiceDocument

_BUDGET_PARTS = ("ek", "zdroj", "oddiel", "trieda", "analytika")


class DocumentRef(Contract):
    """Header of the accounting document."""

    series: str = Field(description="'FD', or 'FDŠJ' for the school canteen")
    number: str | None = Field(default=None, description="e.g. 'FD/144/26'")
    booking_date: dt.date | None = None


class PostingLine(Contract):
    """One line of Zaúčtovanie záväzku."""

    md: AccountKey
    dal: AccountKey
    amount: BookingAmount
    text: str
    stredisko: str | None = None
    transfer: str | None = None


class BudgetLine(Contract):
    """One line of Rozpočet záväzku: the key in the software's format and its five parts,
    which must agree."""

    key: BudgetKey
    ek: Ek
    zdroj: Zdroj
    oddiel: Oddiel
    trieda: Trieda
    analytika: Analytika
    amount: BookingAmount
    text: str
    stredisko: str | None = None
    transfer: str | None = None

    @model_validator(mode="after")
    def _key_matches_parts(self) -> "BudgetLine":
        expected = " ".join(getattr(self, part) for part in _BUDGET_PARTS)
        if self.key != expected:
            raise ValueError(f"key {self.key!r} does not match its parts {expected!r}")
        return self


class Coding(Contract):
    """The document header and both codings, as entered into the software."""

    document: DocumentRef
    posting: list[PostingLine] = Field(min_length=1)
    budget: list[BudgetLine] = Field(min_length=1)


class SupplierRef(Contract):
    name: str | None = None
    ico: Ico | None = None
    known: bool = Field(description="The supplier has precedents in supplier memory")


class InvoiceSummary(Contract):
    number: str | None = None
    issued: dt.date | None = None
    delivered: dt.date | None = None
    due: dt.date | None = None
    vs: str | None = None
    gross: Amount | None = None
    vat: Amount | None = None


class Evidence(Contract):
    field: str
    source: Literal[
        "supplier_memory", "rule", "lexicon", "similarity", "handwritten", "counter", "invoice"
    ]
    detail: str


class Alternative(Contract):
    budget_key: BudgetKey
    md: AccountKey | None = Field(
        default=None, description="Debit account it would bring, so the UI can swap the whole line"
    )
    score: float = Field(ge=0, le=1)
    why: str


class Confidence(Contract):
    overall: float = Field(ge=0, le=1)
    ek: float | None = Field(default=None, ge=0, le=1)
    cofog: float | None = Field(default=None, ge=0, le=1)
    zdroj: float | None = Field(default=None, ge=0, le=1)
    analytika: float | None = Field(default=None, ge=0, le=1)
    md: float | None = Field(default=None, ge=0, le=1)
    dal: float | None = Field(default=None, ge=0, le=1)
    booking_date: float | None = Field(default=None, ge=0, le=1)
    document_number: float | None = Field(default=None, ge=0, le=1)


class Validation(Contract):
    ok: bool
    checks: list[str] = Field(default_factory=list, description="Checks that passed")
    errors: list[str] = Field(default_factory=list, description="Broken invariants; ok is false")
    warnings: list[str] = Field(
        default_factory=list, description="Set needs_review without failing validation"
    )


class CodingProposal(Contract):
    invoice_id: str = Field(description="id of the InvoiceDocument")
    bundle_id: str = Field(description="Reference bundle the codes were checked against")
    document: DocumentRef
    supplier: SupplierRef
    invoice: InvoiceSummary
    posting: list[PostingLine] = Field(
        default_factory=list, description="Empty when the invoice goes to manual entry"
    )
    budget: list[BudgetLine] = Field(default_factory=list)
    confidence: Confidence
    evidence: list[Evidence] = Field(default_factory=list)
    alternatives: list[Alternative] = Field(default_factory=list)
    validation: Validation
    needs_review: bool
    review_reasons: list[str] = Field(
        default_factory=list, description="Why it needs review, e.g. 'credit note, manual entry'"
    )

    def coding(self) -> Coding:
        """The part the accountant types in. Raises for a proposal without lines."""
        return Coding(document=self.document, posting=self.posting, budget=self.budget)


class CodeRequest(Contract):
    """Body of POST /api/code."""

    invoice: InvoiceDocument
    entity: Ico | None = Field(default=None, description="Defaults to the customer IČO")
