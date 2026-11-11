"""Prehľad klientov and Platforma (plan §10.8, §10.9, §2 decision 67).

The provider's overview has one row per active customer assigned to it: the invoices
uploaded in the month with how many of them wait for the check step, need review or failed,
those booked in the month, the last audited activity, the lists the engine needs that are
missing for the month's year, and the import runs still open. The totals come first. Staff
see their own provider's customers only; admins any provider's.

The platform counts: active providers, customers and users; invoices uploaded this month;
pages read by OCR this month; failed jobs; logins in the last 7 days; mail not sent yet.
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from riso.codelists import CodelistsUnitOfWork, missing_required_lists
from riso.identity import Permission
from riso.invoicing import StatisticsUnitOfWork, customer_counts, invoices_uploaded
from riso.reporting.application.dashboard import Month
from riso.shared.context import RequestContext
from riso.tenancy import TenancyUnitOfWork, get_provider

LOGIN_WINDOW = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class PlatformReadsView:
    providers: int
    customers: int
    users: int
    ocr_pages: int
    failed_jobs: int
    logins: int
    login_users: int
    unsent_mail: int


class OverviewReads(Protocol):
    """What the overviews read beyond invoices and code lists, across contexts."""

    def open_imports(self, customer_ids: Collection[str]) -> dict[str, int]:
        """Per customer, its import runs not applied or cancelled yet."""
        ...

    def last_activity(self, customer_ids: Collection[str]) -> dict[str, datetime]:
        """Per customer, its latest audit event (customers without one are left out)."""
        ...

    def platform(
        self, *, month_start: datetime, month_end: datetime, since: datetime
    ) -> PlatformReadsView:
        """The platform's counts but invoices: OCR pages in the month, logins since."""
        ...


class OverviewUnitOfWork(StatisticsUnitOfWork, CodelistsUnitOfWork, TenancyUnitOfWork, Protocol):
    @property
    def overview_reads(self) -> OverviewReads: ...


@dataclass(frozen=True, slots=True)
class OverviewRow:
    customer_id: str
    name: str
    ico: str
    uploaded: int
    waiting: int
    review: int
    failed: int
    booked: int
    last_activity: datetime | None
    missing_lists: tuple[str, ...]
    """The lists the engine needs that the customer has no version of for the year."""
    open_imports: int


@dataclass(frozen=True, slots=True)
class OverviewTotals:
    customers: int
    uploaded: int
    waiting: int
    review: int
    failed: int
    booked: int
    missing_lists: int
    """Customers missing a list."""
    open_imports: int


@dataclass(frozen=True, slots=True)
class ProviderOverviewView:
    provider_id: str
    provider_name: str
    month: str
    totals: OverviewTotals
    rows: list[OverviewRow]
    """By name."""


@dataclass(frozen=True, slots=True)
class PlatformCountsView:
    month: str
    providers: int
    customers: int
    users: int
    invoices: int
    """Uploaded this month."""
    ocr_pages: int
    """Read by OCR this month."""
    failed_jobs: int
    logins: int
    """In the last 7 days."""
    login_users: int
    """Different users among them."""
    unsent_mail: int


def provider_overview(
    ctx: RequestContext,
    uow_factory: Callable[[], OverviewUnitOfWork],
    provider_id: str,
    month: Month,
) -> ProviderOverviewView:
    ctx.require(Permission.PROVIDER_OVERVIEW, provider_id=provider_id)
    provider = get_provider(ctx, uow_factory(), provider_id)
    ids = [c.id for c in provider.customers]
    counts = customer_counts(uow_factory(), ids, month.start, month.end)
    uow = uow_factory()
    with uow:
        missing = {i: tuple(missing_required_lists(uow, i, month.year)) for i in ids}
        imports = uow.overview_reads.open_imports(ids)
        activity = uow.overview_reads.last_activity(ids)
    rows = [
        OverviewRow(
            customer_id=c.id,
            name=c.name,
            ico=c.ico,
            uploaded=counts[c.id].uploaded,
            waiting=counts[c.id].by_state.get("extracted", 0),
            review=counts[c.id].by_state.get("needs_review", 0),
            failed=counts[c.id].by_state.get("extraction_failed", 0),
            booked=counts[c.id].booked,
            last_activity=activity.get(c.id),
            missing_lists=missing[c.id],
            open_imports=imports.get(c.id, 0),
        )
        for c in sorted(provider.customers, key=lambda c: (c.name.casefold(), c.id))
    ]
    totals = OverviewTotals(
        customers=len(rows),
        uploaded=sum(r.uploaded for r in rows),
        waiting=sum(r.waiting for r in rows),
        review=sum(r.review for r in rows),
        failed=sum(r.failed for r in rows),
        booked=sum(r.booked for r in rows),
        missing_lists=sum(1 for r in rows if r.missing_lists),
        open_imports=sum(r.open_imports for r in rows),
    )
    return ProviderOverviewView(
        provider.provider.id, provider.provider.name, str(month), totals, rows
    )


def platform_counts(
    ctx: RequestContext, uow_factory: Callable[[], OverviewUnitOfWork], month: Month
) -> PlatformCountsView:
    ctx.require(Permission.PLATFORM_OVERVIEW)
    invoices = invoices_uploaded(uow_factory(), month.start, month.end)
    uow = uow_factory()
    with uow:
        reads = uow.overview_reads.platform(
            month_start=month.start, month_end=month.end, since=uow.clock.now() - LOGIN_WINDOW
        )
    return PlatformCountsView(
        month=str(month),
        providers=reads.providers,
        customers=reads.customers,
        users=reads.users,
        invoices=invoices,
        ocr_pages=reads.ocr_pages,
        failed_jobs=reads.failed_jobs,
        logins=reads.logins,
        login_users=reads.login_users,
        unsent_mail=reads.unsent_mail,
    )
