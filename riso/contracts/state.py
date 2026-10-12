"""Supplier memory and document counters: what the engine keeps between invoices
(plan sections 3.2 and 3.3)."""

import datetime as dt
import re
from collections import Counter
from typing import Literal

from pydantic import Field, field_validator, model_validator

from riso.contracts.base import AccountKey, BookingAmount, BudgetKey, Contract, Ico

_COUNTER_KEY = re.compile(r"^[^/\s]+/\d{4}$")


class PrecedentLine(Contract):
    budget_key: BudgetKey
    md: AccountKey
    dal: AccountKey
    budget_text: str
    posting_text: str


class Precedent(Contract):
    """One past coding of a supplier's invoice."""

    document_number: str | None = None
    booking_date: dt.date | None = None
    amount: BookingAmount | None = None
    lines: list[PrecedentLine] = Field(min_length=1)
    source: Literal["screenshot", "feedback"]


class SupplierRecord(Contract):
    ico: Ico
    name: str
    precedents: list[Precedent] = Field(min_length=1)


class SupplierMemory(Contract):
    entity_ico: Ico
    suppliers: list[SupplierRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_record_per_supplier(self) -> "SupplierMemory":
        repeated = sorted(ico for ico, n in Counter(s.ico for s in self.suppliers).items() if n > 1)
        if repeated:
            raise ValueError(f"suppliers repeat IČO {repeated}")
        return self

    def find(self, ico: str) -> SupplierRecord | None:
        return next((s for s in self.suppliers if s.ico == ico), None)


class Counters(Contract):
    """Fallback numbering for scans whose handwritten number the OCR could not read, and the
    numbers already taken, for duplicate detection."""

    entity_ico: Ico
    last_used: dict[str, int] = Field(
        description="Last sequence number per '<series>/<year>', e.g. 'FD/2026': 222"
    )
    used_numbers: list[str] = Field(
        default_factory=list, description="Document numbers already taken, e.g. 'FD/183/26'"
    )

    @field_validator("last_used")
    @classmethod
    def _series_year_keys(cls, value: dict[str, int]) -> dict[str, int]:
        for key, number in value.items():
            if not _COUNTER_KEY.match(key):
                raise ValueError(f"counter key {key!r} is not '<series>/<year>'")
            if number < 0:
                raise ValueError(f"counter {key!r} is negative")
        return value
