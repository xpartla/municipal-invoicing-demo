"""The application's unit of work: every context's repositories on one session.

Each context's use cases ask for the unit of work they need through a protocol
(`IdentityUnitOfWork`, `TenancyUnitOfWork`, …); this class satisfies all of them, so a
command that touches several contexts (removing a provider deactivates its staff) commits
once. It lives in the composition root, the one place that may import every context's
infrastructure.
"""

from riso.identity.infrastructure.uow import SqlIdentityUnitOfWork
from riso.tenancy.infrastructure.uow import SqlTenancyUnitOfWork


class AppUnitOfWork(SqlIdentityUnitOfWork, SqlTenancyUnitOfWork):
    def _start(self) -> None:
        SqlIdentityUnitOfWork._start(self)
        SqlTenancyUnitOfWork._start(self)
