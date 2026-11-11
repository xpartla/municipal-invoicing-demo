"""The reporting context's `OverviewReads` port on the database: counts across several
contexts' tables for Prehľad klientov and Platforma (plan §10.8, §10.9). It lives in the
composition root, the one place that may read every context's tables; each query is
portable SQL."""

from collections.abc import Collection
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from riso.audit.infrastructure.orm import AuditEventRow
from riso.exchange.infrastructure.orm import ImportRunRow
from riso.identity.infrastructure.orm import UserRow
from riso.intake.infrastructure.orm import DocumentRow, ExtractionRow
from riso.jobs.infrastructure.orm import JobRow
from riso.platform.mail import MailOutboxRow
from riso.reporting.application import PlatformReadsView
from riso.tenancy.infrastructure.orm import CustomerRow, ServiceProviderRow

CLOSED_IMPORTS = ("applied", "cancelled")
LOGIN = "auth.login"


class SqlOverviewReads:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _count(self, statement: Select[int]) -> int:
        return int(self._session.scalar(statement) or 0)

    def open_imports(self, customer_ids: Collection[str]) -> dict[str, int]:
        if not customer_ids:
            return {}
        rows = self._session.execute(
            select(ImportRunRow.customer_id, func.count())
            .where(
                ImportRunRow.customer_id.in_(list(customer_ids)),
                ImportRunRow.state.not_in(CLOSED_IMPORTS),
            )
            .group_by(ImportRunRow.customer_id)
        )
        return {customer_id: count for customer_id, count in rows if customer_id}

    def last_activity(self, customer_ids: Collection[str]) -> dict[str, datetime]:
        if not customer_ids:
            return {}
        rows = self._session.execute(
            select(AuditEventRow.customer_id, func.max(AuditEventRow.at))
            .where(AuditEventRow.customer_id.in_(list(customer_ids)))
            .group_by(AuditEventRow.customer_id)
        )
        return {customer_id: at for customer_id, at in rows if customer_id and at}

    def platform(
        self, *, month_start: datetime, month_end: datetime, since: datetime
    ) -> PlatformReadsView:
        s = self._session
        logins = s.execute(
            select(func.count(), func.count(func.distinct(AuditEventRow.actor_id))).where(
                AuditEventRow.action == LOGIN, AuditEventRow.at >= since
            )
        ).one()
        pages = s.scalar(
            select(func.sum(func.coalesce(DocumentRow.pages, 1)))
            .select_from(ExtractionRow)
            .join(DocumentRow, DocumentRow.id == ExtractionRow.document_id)
            .where(
                ExtractionRow.source == "ocr",
                ExtractionRow.created_at >= month_start,
                ExtractionRow.created_at < month_end,
            )
        )
        return PlatformReadsView(
            providers=self._count(
                select(func.count())
                .select_from(ServiceProviderRow)
                .where(ServiceProviderRow.status == "active")
            ),
            customers=self._count(
                select(func.count()).select_from(CustomerRow).where(CustomerRow.status == "active")
            ),
            users=self._count(
                select(func.count())
                .select_from(UserRow)
                .where(UserRow.status.in_(["invited", "active"]))
            ),
            ocr_pages=int(pages or 0),
            failed_jobs=self._count(
                select(func.count()).select_from(JobRow).where(JobRow.status == "failed")
            ),
            logins=int(logins[0] or 0),
            login_users=int(logins[1] or 0),
            unsent_mail=self._count(
                select(func.count())
                .select_from(MailOutboxRow)
                .where(MailOutboxRow.sent_at.is_(None))
            ),
        )
