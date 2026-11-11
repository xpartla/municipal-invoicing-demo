"""The application's unit of work: every context's repositories on one session.

Each context's use cases ask for the unit of work they need through a protocol
(`IdentityUnitOfWork`, `TenancyUnitOfWork`, …); this class satisfies all of them, so a
command that touches several contexts (removing a provider deactivates its staff) commits
once. It lives in the composition root, the one place that may import every context's
infrastructure.
"""

from riso.api.adapters import CodelistSeriesPatterns, UowPrecedents, UserLogins, UserNames
from riso.audit.infrastructure.log import SqlAuditLog, SqlAuditRecorder
from riso.codelists.infrastructure.uow import SqlCodelistsUnitOfWork
from riso.exchange.infrastructure.repository import (
    SqlExportRunRepository,
    SqlImportRunRepository,
    SqlTemplateRepository,
)
from riso.identity.infrastructure.uow import SqlIdentityUnitOfWork
from riso.intake.infrastructure.repository import SqlDocumentRepository, SqlExtractionRepository
from riso.invoicing.infrastructure.queries import SqlInvoiceQueries
from riso.invoicing.infrastructure.uow import SqlInvoicingUnitOfWork
from riso.jobs import JobRegistry, register_builtin
from riso.jobs.application import RepositoryJobQueue
from riso.jobs.infrastructure.repository import SqlJobRepository
from riso.platform.db import Database
from riso.platform.mail import MailTemplates, OutboxMailSender, OutboxQueries, TemplateMailer
from riso.shared.clock import Clock
from riso.shared.events import EventDispatcher
from riso.shared.ids import IdGenerator
from riso.tenancy.infrastructure.uow import SqlTenancyUnitOfWork

TEMPLATES = MailTemplates()


class AppUnitOfWork(
    SqlIdentityUnitOfWork,
    SqlTenancyUnitOfWork,
    SqlCodelistsUnitOfWork,
    SqlInvoicingUnitOfWork,
):
    mailer: TemplateMailer
    outbox: OutboxQueries
    audit: SqlAuditRecorder
    audit_log: SqlAuditLog
    logins: UserLogins
    imports: SqlImportRunRepository
    templates: SqlTemplateRepository
    exports: SqlExportRunRepository
    documents: SqlDocumentRepository
    extractions: SqlExtractionRepository
    queue: RepositoryJobQueue
    """Jobs queued here are committed with the change that needs them."""
    series_patterns: CodelistSeriesPatterns
    precedents: UowPrecedents
    invoice_queries: SqlInvoiceQueries
    people: UserNames

    def __init__(
        self,
        db: Database,
        *,
        clock: Clock,
        ids: IdGenerator,
        dispatcher: EventDispatcher | None = None,
        immediate: bool = True,
        registry: JobRegistry | None = None,
    ) -> None:
        super().__init__(db, clock=clock, ids=ids, dispatcher=dispatcher, immediate=immediate)
        self._registry = registry or register_builtin(JobRegistry())

    def _start(self) -> None:
        SqlIdentityUnitOfWork._start(self)
        SqlTenancyUnitOfWork._start(self)
        SqlCodelistsUnitOfWork._start(self)
        SqlInvoicingUnitOfWork._start(self)
        self.imports = SqlImportRunRepository(self.session, self)
        self.templates = SqlTemplateRepository(self.session, self)
        self.exports = SqlExportRunRepository(self.session, self)
        self.documents = SqlDocumentRepository(self.session, self)
        self.extractions = SqlExtractionRepository(self.session, self)
        self.queue = RepositoryJobQueue(
            SqlJobRepository(self.session), self._registry, self.clock, self.ids
        )
        self.mailer = TemplateMailer(
            TEMPLATES, OutboxMailSender(self.session, self.clock, self.ids)
        )
        self.outbox = OutboxQueries(self.session)
        self.audit = SqlAuditRecorder(self.session, self.clock, self.ids)
        self.audit_log = SqlAuditLog(self.session)
        self.logins = UserLogins(self.users, self.clock)
        self.series_patterns = CodelistSeriesPatterns(self)
        self.precedents = UowPrecedents(self)
        self.invoice_queries = SqlInvoiceQueries(self.session)
        self.people = UserNames(self.users)
