"""The application's unit of work: every context's repositories on one session.

Each context's use cases ask for the unit of work they need through a protocol
(`IdentityUnitOfWork`, `TenancyUnitOfWork`, …); this class satisfies all of them, so a
command that touches several contexts (removing a provider deactivates its staff) commits
once. It lives in the composition root, the one place that may import every context's
infrastructure.
"""

from riso.api.adapters import UserLogins
from riso.audit.infrastructure.log import SqlAuditLog, SqlAuditRecorder
from riso.identity.infrastructure.uow import SqlIdentityUnitOfWork
from riso.platform.mail import MailTemplates, OutboxMailSender, OutboxQueries, TemplateMailer
from riso.tenancy.infrastructure.uow import SqlTenancyUnitOfWork

TEMPLATES = MailTemplates()


class AppUnitOfWork(SqlIdentityUnitOfWork, SqlTenancyUnitOfWork):
    mailer: TemplateMailer
    outbox: OutboxQueries
    audit: SqlAuditRecorder
    audit_log: SqlAuditLog
    logins: UserLogins

    def _start(self) -> None:
        SqlIdentityUnitOfWork._start(self)
        SqlTenancyUnitOfWork._start(self)
        self.mailer = TemplateMailer(
            TEMPLATES, OutboxMailSender(self.session, self.clock, self.ids)
        )
        self.outbox = OutboxQueries(self.session)
        self.audit = SqlAuditRecorder(self.session, self.clock, self.ids)
        self.audit_log = SqlAuditLog(self.session)
        self.logins = UserLogins(self.users, self.clock)
