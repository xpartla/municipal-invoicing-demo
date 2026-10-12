"""Feedback: the accountant's verdict on one proposal (plan stage S8)."""

import datetime as dt
from typing import Literal

from pydantic import Field, model_validator

from riso.contracts.base import Contract, Ico
from riso.contracts.proposal import Coding, CodingProposal


class Feedback(Contract):
    invoice_id: str
    bundle_id: str
    action: Literal["accepted", "corrected"]
    proposal: CodingProposal = Field(description="What the engine proposed")
    final: Coding = Field(description="What the accountant entered into the software")
    supplier_ico: Ico | None = None
    received_at: dt.datetime | None = Field(default=None, description="Set by the server")
    note: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "Feedback":
        if self.invoice_id != self.proposal.invoice_id:
            raise ValueError("invoice_id differs from the proposal's")
        if self.bundle_id != self.proposal.bundle_id:
            raise ValueError("bundle_id differs from the proposal's")
        if self.action == "accepted" and self.final != self.proposal.coding():
            raise ValueError("an accepted proposal keeps its coding; use 'corrected'")
        return self
