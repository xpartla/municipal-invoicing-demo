"""The identity unit of work on SQLAlchemy."""

from riso.identity.infrastructure.repository import SqlUserRepository
from riso.identity.infrastructure.sessions import SqlLoginAttemptRepository, SqlSessionRepository
from riso.identity.infrastructure.tokens import SqlTokenRepository
from riso.platform.uow import SqlUnitOfWork


class SqlIdentityUnitOfWork(SqlUnitOfWork):
    users: SqlUserRepository
    sessions: SqlSessionRepository
    login_attempts: SqlLoginAttemptRepository
    tokens: SqlTokenRepository

    def _start(self) -> None:
        self.users = SqlUserRepository(self.session, self)
        self.sessions = SqlSessionRepository(self.session)
        self.login_attempts = SqlLoginAttemptRepository(self.session)
        self.tokens = SqlTokenRepository(self.session)
