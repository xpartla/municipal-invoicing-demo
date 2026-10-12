"""ReferenceBundle: one entity's dictionaries exported from the accounting software
(plan section 3.2)."""

from collections import Counter
from typing import Literal

from pydantic import Field, model_validator

from riso.contracts.base import (
    AccountKey,
    Analytika,
    Au,
    Contract,
    Ek,
    Ico,
    Oddiel,
    Period,
    Su,
    Trieda,
    Zdroj,
)

AccountType = Literal["active", "passive", "cost", "revenue"]


def budget_key(ek: str, zdroj: str, oddiel: str | None, trieda: str | None, analytika: str) -> str:
    """The key in the software's own format, '637005 41 01 110 000'. Income positions have
    no function code, so theirs is 'EK zdroj analytika'."""
    if oddiel is None or trieda is None:
        return f"{ek} {zdroj} {analytika}"
    return f"{ek} {zdroj} {oddiel} {trieda} {analytika}"


class Entity(Contract):
    ico: Ico
    name: str
    address: str | None = None


class Account(Contract):
    key: AccountKey = Field(description="'SU AU', e.g. '518 001'")
    su: Su
    au: Au
    type: AccountType
    activity: str | None = None
    description: str | None = None
    row: int = Field(description="Row in the exported sheet")

    @model_validator(mode="after")
    def _key_matches_parts(self) -> "Account":
        if self.key != f"{self.su} {self.au}":
            raise ValueError(f"key {self.key!r} does not match SU {self.su} and AU {self.au}")
        return self


class BudgetPosition(Contract):
    key: str = Field(
        description="'EK zdroj oddiel trieda analytika', or 'EK zdroj analytika' for income"
    )
    ek: Ek
    zdroj: Zdroj
    oddiel: Oddiel | None = None
    trieda: Trieda | None = None
    analytika: Analytika
    description: str | None = None
    aliases: list[str] = Field(
        default_factory=list,
        description="Descriptions of further rows merged into this one because they share the key",
    )
    rows: list[int] = Field(min_length=1, description="Rows in the exported sheet")

    @model_validator(mode="after")
    def _key_matches_parts(self) -> "BudgetPosition":
        if (self.oddiel is None) != (self.trieda is None):
            raise ValueError("oddiel and trieda are either both set or both empty")
        expected = budget_key(self.ek, self.zdroj, self.oddiel, self.trieda, self.analytika)
        if self.key != expected:
            raise ValueError(f"key {self.key!r} does not match its parts {expected!r}")
        return self


class DocumentSeries(Contract):
    code: str = Field(description="Prefix of the pattern, e.g. 'FD' or 'FDŠJ'")
    series_id: str = Field(description="'Evidenčné číslo' in the software")
    pattern: str = Field(description="e.g. 'FD/XXX/RR': X the sequence, RR the year, MM the month")
    description: str
    bank_account: str | None = None


class Transfer(Contract):
    id: str = Field(description="Income-side key the transfer comes from, e.g. '312001 11H 012'")
    name: str
    zdroj: Zdroj
    mock: bool = Field(
        default=True, description="Derived from the income side; the real list was not exported"
    )


class CostCentre(Contract):
    code: str
    name: str


class SourceFile(Contract):
    name: str
    sha256: str
    data_rows: int


class IngestWarning(Contract):
    code: Literal["duplicate_key", "missing_description", "skipped_row"]
    source: str
    rows: list[int]
    message: str


class ReferenceBundle(Contract):
    bundle_id: str = Field(description="'<IČO>/<period>', e.g. '00305863/2026-08'")
    entity: Entity
    period: Period
    sources: list[SourceFile]
    accounts: list[Account]
    budget_positions_expense: list[BudgetPosition]
    budget_positions_income: list[BudgetPosition]
    document_series: list[DocumentSeries]
    transfers: list[Transfer]
    cost_centres: list[CostCentre] = Field(
        default_factory=list, description="The stredisko list; not exported, so empty in the demo"
    )
    warnings: list[IngestWarning] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> "ReferenceBundle":
        if self.bundle_id != f"{self.entity.ico}/{self.period}":
            raise ValueError(f"bundle_id {self.bundle_id!r} is not '<IČO>/<period>'")
        for name, keys in (
            ("accounts", [a.key for a in self.accounts]),
            ("budget_positions_expense", [p.key for p in self.budget_positions_expense]),
            ("budget_positions_income", [p.key for p in self.budget_positions_income]),
            ("document_series", [s.code for s in self.document_series]),
            ("transfers", [t.id for t in self.transfers]),
            ("cost_centres", [c.code for c in self.cost_centres]),
        ):
            repeated = sorted(key for key, count in Counter(keys).items() if count > 1)
            if repeated:
                raise ValueError(f"{name} repeat keys {repeated}")
        if any(p.oddiel is None for p in self.budget_positions_expense):
            raise ValueError("every expense position needs oddiel and trieda")
        return self
