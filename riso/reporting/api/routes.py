"""The reporting API: the customer's dashboard (Domov) and storage listing (Úložisko)."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from riso.api.deps import Caller, ServicesDep, check_csrf, customer_context
from riso.contracts.base import BookingAmount
from riso.identity import Permission
from riso.reporting.application import (
    DashboardView,
    FileKind,
    FileListing,
    Month,
    customer_dashboard,
    list_files,
)
from riso.shared.clock import local_date
from riso.shared.errors import ValidationFailed

router = APIRouter(prefix="/api", dependencies=[Depends(check_csrf)], tags=["reporting"])

MAX_PAGE = 200


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FileOut(_Out):
    kind: FileKind
    id: str
    name: str
    media_type: str
    size: int
    created_at: datetime
    created_by: str | None
    invoice_id: str | None
    detail: str | None


class KindTotalOut(_Out):
    count: int
    size: int


class FilesOut(_Out):
    """The page of files (`items`) of `total` matching ones; `size` and `kinds` count every
    file of the customer. A file downloads through its owner: `documents.file`,
    `imports.file` or `exports.file` with the file's `id`."""

    items: list[FileOut]
    total: int
    size: int
    kinds: dict[FileKind, KindTotalOut]

    @classmethod
    def of(cls, listing: FileListing) -> "FilesOut":
        return cls(
            items=[
                FileOut(
                    kind=f.kind,
                    id=f.id,
                    name=f.name,
                    media_type=f.media_type,
                    size=f.size,
                    created_at=f.created_at,
                    created_by=f.created_by,
                    invoice_id=f.invoice_id,
                    detail=f.detail,
                )
                for f in listing.items
            ],
            total=listing.total,
            size=listing.size,
            kinds={k: KindTotalOut(count=t.count, size=t.size) for k, t in listing.kinds.items()},
        )


@router.get("/customers/{customer_id}/files", name="files.list")
def files(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
    kind: FileKind | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
) -> FilesOut:
    """Every file the customer's storage keeps (Úložisko), the newest first: uploaded
    invoices (`document`, with the invoice), import files and export files."""
    listing = list_files(
        caller.ctx,
        lambda: services.uow(immediate=False),
        customer_id,
        kind=kind,
        offset=(page - 1) * size,
        limit=size,
    )
    return FilesOut.of(listing)


class TilesOut(_Out):
    uploaded: int = Field(description="Uploaded in the month")
    waiting: int = Field(description="Of those, extracted and waiting for the check step")
    review: int = Field(description="Of those, needing review")
    failed: int = Field(description="Of those, whose extraction failed")
    booked: int = Field(description="Booked in riso in the month (booked, exported or paid)")
    booked_total: BookingAmount = Field(description="Their gross, credit notes negative")


class DayTotalOut(_Out):
    day: date
    count: int
    total: BookingAmount


class TypeTotalOut(_Out):
    series: str | None
    credit_note: bool
    count: int
    total: BookingAmount


class SupplierTotalOut(_Out):
    ico: str | None
    name: str | None
    count: int
    total: BookingAmount


class UnitTotalOut(_Out):
    function: str = Field(description="Oddiel and trieda: `09 111`")
    code: str | None = Field(description="The COFOG code: `09.1.1.1`")
    name: str | None
    invoices: int
    total: BookingAmount = Field(description="The function's booked lines")


class MonthTotalOut(_Out):
    month: str = Field(description="`2026-11`")
    count: int
    total: BookingAmount


class ReviewOut(_Out):
    booked: int
    reviewed: int = Field(description="Booked invoices whose proposal needed review")
    rate: float | None = Field(description="reviewed / booked; none without bookings")
    median_seconds: int | None = Field(description="From upload to booking")


class BudgetRowOut(_Out):
    key: str
    description: str | None
    budgeted: BookingAmount = Field(description="Adjusted, else approved")
    drawn: BookingAmount
    share: float | None


class BudgetOut(_Out):
    year: int
    rows: list[BudgetRowOut]
    budgeted: BookingAmount
    drawn: BookingAmount
    elsewhere: BookingAmount = Field(description="Drawn on positions without an amount")


class AttentionItemOut(_Out):
    id: str
    state: str
    supplier_name: str | None
    source_ref: str | None
    uploaded_at: datetime


class WarningOut(_Out):
    code: str = Field(description="A knowledge health code: `list_missing` …")
    subject: str
    kind: str | None


class AttentionOut(_Out):
    failed: list[AttentionItemOut]
    failed_total: int
    waiting: list[AttentionItemOut]
    waiting_total: int
    warnings: list[WarningOut]


class OnboardingOut(_Out):
    year: int
    profile: bool
    codelists: bool
    health: bool
    first_booked: bool
    done: bool


class DashboardOut(_Out):
    """Domov (plan §10.2, decision 67). A month is a Bratislava month; booked statistics
    count bookings made in riso in it; `attention` and `onboarding` are about now."""

    month: str
    tiles: TilesOut
    per_day: list[DayTotalOut]
    by_type: list[TypeTotalOut]
    suppliers_by_count: list[SupplierTotalOut]
    suppliers_by_amount: list[SupplierTotalOut]
    units: list[UnitTotalOut]
    months: list[MonthTotalOut] = Field(description="The twelve months ending with this one")
    review: ReviewOut
    budget: BudgetOut | None = Field(description="None when the budget has no amounts")
    attention: AttentionOut
    onboarding: OnboardingOut

    @classmethod
    def of(cls, view: DashboardView) -> "DashboardOut":
        stats = view.statistics
        budget = view.budget
        return cls(
            month=view.month,
            tiles=TilesOut.model_validate(stats.tiles, from_attributes=True),
            per_day=[DayTotalOut.model_validate(d, from_attributes=True) for d in stats.per_day],
            by_type=[TypeTotalOut.model_validate(t, from_attributes=True) for t in stats.by_type],
            suppliers_by_count=[
                SupplierTotalOut.model_validate(s, from_attributes=True)
                for s in stats.suppliers_by_count
            ],
            suppliers_by_amount=[
                SupplierTotalOut.model_validate(s, from_attributes=True)
                for s in stats.suppliers_by_amount
            ],
            units=[UnitTotalOut.model_validate(u, from_attributes=True) for u in stats.units],
            months=[MonthTotalOut.model_validate(m, from_attributes=True) for m in stats.months],
            review=ReviewOut(
                booked=stats.review.booked,
                reviewed=stats.review.reviewed,
                rate=stats.review.rate,
                median_seconds=stats.review.median_seconds,
            ),
            budget=None
            if budget is None
            else BudgetOut(
                year=budget.year,
                rows=[
                    BudgetRowOut(
                        key=r.key,
                        description=r.description,
                        budgeted=r.budgeted,
                        drawn=r.drawn,
                        share=r.share,
                    )
                    for r in budget.rows
                ],
                budgeted=budget.budgeted,
                drawn=budget.drawn,
                elsewhere=budget.elsewhere,
            ),
            attention=AttentionOut(
                failed=[
                    AttentionItemOut.model_validate(i, from_attributes=True)
                    for i in view.attention.failed
                ],
                failed_total=view.attention.failed_total,
                waiting=[
                    AttentionItemOut.model_validate(i, from_attributes=True)
                    for i in view.attention.waiting
                ],
                waiting_total=view.attention.waiting_total,
                warnings=[
                    WarningOut.model_validate(w, from_attributes=True)
                    for w in view.attention.warnings
                ],
            ),
            onboarding=OnboardingOut(
                year=view.onboarding.year,
                profile=view.onboarding.profile,
                codelists=view.onboarding.codelists,
                health=view.onboarding.health,
                first_booked=view.onboarding.first_booked,
                done=view.onboarding.done,
            ),
        )


@router.get("/customers/{customer_id}/dashboard", name="dashboard.get")
def dashboard(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
    month: Annotated[
        str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="`2026-11`; default: now")
    ] = None,
) -> DashboardOut:
    """Domov's numbers for a month (plan §10.2): the tiles, the charts and tables, the
    budget drawdown, what needs attention and the onboarding checklist."""
    try:
        chosen = Month.parse(month) if month else Month.of(local_date(services.clock.now()))
    except ValueError as exc:
        raise ValidationFailed.on("month", str(exc)) from exc
    view = customer_dashboard(
        caller.ctx, lambda: services.uow(immediate=False), customer_id, chosen
    )
    return DashboardOut.of(view)
