"""The codelists unit of work on SQLAlchemy."""

from riso.codelists.infrastructure.repository import SqlCodeListRepository
from riso.platform.uow import SqlUnitOfWork


class SqlCodelistsUnitOfWork(SqlUnitOfWork):
    codelists: SqlCodeListRepository

    def _start(self) -> None:
        self.codelists = SqlCodeListRepository(self.session, self)
