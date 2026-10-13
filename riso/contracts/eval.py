"""EvalReport: the metrics of plan section 9 over one split of the dataset, with the result of
every case, as `riso eval` prints them and `GET /api/eval` returns them."""

import datetime as dt
from typing import Literal

from pydantic import Field

from riso.contracts.base import AccountKey, BudgetKey, Contract, Ico, Slug

Split = Literal["anchor", "seed", "heldout"]


class Rate(Contract):
    hits: int = Field(ge=0)
    n: int = Field(ge=0, description="Cases the metric applies to")
    value: float | None = Field(description="hits / n, null when n is 0")


class LineCodes(Contract):
    """What the accountant types for one line: the budget key, MD and DAL."""

    key: BudgetKey
    md: AccountKey
    dal: AccountKey


class CaseResult(Contract):
    case_id: Slug
    tags: list[Slug] = Field(default_factory=list)
    supplier: str | None = None
    known_supplier: bool = Field(description="The supplier had precedents when it was coded")
    expected_outcome: Literal["coded", "manual_entry"]
    expected: list[LineCodes] = Field(default_factory=list)
    proposed: list[LineCodes] = Field(default_factory=list)
    alternatives: list[BudgetKey] = Field(
        default_factory=list, description="The proposal's alternatives, best first"
    )
    correct: bool = Field(
        description="The expected outcome is reproduced: every line's key, MD and DAL, or "
        "manual entry, and the number and booking date wherever the scan shows them"
    )
    full_key: bool | None = Field(description="Every budget key matches; null for manual entry")
    fields: dict[str, bool] = Field(
        default_factory=dict,
        description="Per field (ek, zdroj, cofog, analytika, md, dal): every line matches",
    )
    top3: bool | None = Field(
        default=None,
        description="The expected key is the chosen one or among the first two "
        "alternatives; single-line codings only",
    )
    split_ok: bool | None = Field(
        default=None, description="As many lines as expected; null for manual entry"
    )
    validation_ok: bool | None = Field(
        default=None, description="Null when the proposal has no lines"
    )
    number_ok: bool | None = Field(
        default=None, description="Null when the scan's number is unreadable"
    )
    date_ok: bool | None = Field(
        default=None, description="Null when the scan's booking date is unreadable"
    )
    needs_review: bool
    expected_review: bool | None = None
    review_reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class Target(Contract):
    metric: str
    target: float
    value: float | None
    met: bool


class EvalReport(Contract):
    entity_ico: Ico
    split: Split
    memory: Literal["frozen", "online"] = Field(
        description="frozen: the anchor and seed cases feed supplier memory before any case is "
        "coded, and the coded cases never do (held-out). online: the cases are coded in "
        "booking-date order and each one feeds memory after it is coded (anchor, seed)"
    )
    generated_at: dt.datetime
    engine_version: str
    bundle_id: str
    dataset_sha256: str = Field(description="Digest of the evaluated split's case files")
    precedent_cases: int = Field(description="Dataset cases fed into supplier memory")
    metrics: dict[str, Rate]
    targets: list[Target]
    by_supplier: dict[str, dict[str, Rate]] = Field(description="'known' and 'new' suppliers")
    by_tag: dict[str, dict[str, Rate]]
    cases: list[CaseResult]
