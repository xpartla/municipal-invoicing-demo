"""The identity unit of work on SQLAlchemy."""

from riso.identity.infrastructure.repository import SqlUserRepository
from riso.platform.uow import SqlUnitOfWork


class SqlIdentityUnitOfWork(SqlUnitOfWork):
    users: SqlUserRepository

    def _start(self) -> None:
        self.users = SqlUserRepository(self.session, self)
