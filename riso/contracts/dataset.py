"""DatasetCase: one invoice of the mock dataset and its expected outcome (plan section 7)."""

from typing import Literal

from pydantic import Field, model_validator

from riso.contracts.base import Contract, Slug
from riso.contracts.invoice import InvoiceDocument
from riso.contracts.proposal import Coding


class ExpectedOutcome(Contract):
    outcome: Literal["coded", "manual_entry"]
    coding: Coding | None = None
    needs_review: bool | None = Field(
        default=None, description="Expected review flag, for cases built to test it"
    )

    @model_validator(mode="after")
    def _coding_when_coded(self) -> "ExpectedOutcome":
        if (self.outcome == "coded") != (self.coding is not None):
            raise ValueError("a coded outcome has a coding, a manual entry has none")
        return self


class DatasetCase(Contract):
    id: Slug
    split: Literal["anchor", "seed", "heldout"] = Field(
        description="Anchor and seed cases may feed supplier memory, held-out cases never do"
    )
    invoice: InvoiceDocument
    expected: ExpectedOutcome
    tags: list[Slug] = Field(
        default_factory=list,
        description="Family and edge-case tags for the per-tag metrics, from riso.dataset.TAGS",
    )
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ids_match(self) -> "DatasetCase":
        if self.id != self.invoice.id:
            raise ValueError(f"case id {self.id!r} differs from invoice id {self.invoice.id!r}")
        return self
