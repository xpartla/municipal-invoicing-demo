"""Intermediate structures passed between the pipeline stages (plan section 5)."""

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from riso.contracts import EntityContext, Evidence, InvoiceDocument, SupplierRecord


class StageResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NormalisedInvoice(StageResult):
    """S1: the invoice with clean values, plus diacritics-free tokens for matching."""

    document: InvoiceDocument
    supplier_ico: str | None
    customer_ico: str | None
    gross: Decimal | None
    vat_payer: bool | None
    booking_date: dt.date | None
    handwritten_number: int | None
    is_credit_note: bool
    tokens: tuple[str, ...]
    line_tokens: tuple[tuple[str, ...], ...]


class ResolvedContext(StageResult):
    """S2: whose dictionaries apply, what is known about the supplier, and the header."""

    entity: EntityContext
    bundle_id: str
    supplier: SupplierRecord | None
    series: str
    document_number: str | None
    number_source: Literal["handwritten", "counter"] | None
    booking_date: dt.date | None


class Candidate(StageResult):
    """S3: one budget position a generator proposes, with what supports it."""

    budget_key: str
    score: float
    evidence: tuple[Evidence, ...]
    invoice_line: int | None = None


class ChosenLine(StageResult):
    budget_key: str
    amount: Decimal
    confidence: float
    invoice_line: int | None = None


class Decision(StageResult):
    """S4: the chosen budget line or lines, or the best candidate flagged for review."""

    lines: tuple[ChosenLine, ...]
    alternatives: tuple[Candidate, ...]
    split: bool
    needs_review: bool
    reasons: tuple[str, ...]
