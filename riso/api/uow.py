"""The application's unit of work: every context's repositories on one session.

Each context's use cases ask for the unit of work they need through a protocol
(`IdentityUnitOfWork`, `TenancyUnitOfWork`, …); this class satisfies all of them, so a
command that touches several contexts (removing a provider deactivates its staff) commits
once. It lives in the composition root, the one place that may import every context's
infrastructure.
"""

from riso.api.adapters import UserLogins
from riso.audit.infrastructure.log import SqlAuditLog, SqlAuditRecorder
from riso.codelists.infrastructure.uow import SqlCodelistsUnitOfWork
from riso.exchange.infrastructure.repository import SqlImportRunRepository
from riso.identity.infrastructure.uow import SqlIdentityUnitOfWork
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


class AppUnitOfWork(SqlIdentityUnitOfWork, SqlTenancyUnitOfWork, SqlCodelistsUnitOfWork):
    mailer: TemplateMailer
    outbox: OutboxQueries
    audit: SqlAuditRecorder
    audit_log: SqlAuditLog
    logins: UserLogins
    imports: SqlImportRunRepository
    queue: RepositoryJobQueue
    """Jobs queued here are committed with the change that needs them."""

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
        self.imports = SqlImportRunRepository(self.session, self)
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
