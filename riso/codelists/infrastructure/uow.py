"""The codelists unit of work on SQLAlchemy."""

from riso.codelists.infrastructure.repository import (
    SqlCodeListRepository,
    SqlConventionsRepository,
)
from riso.platform.uow import SqlUnitOfWork


class SqlCodelistsUnitOfWork(SqlUnitOfWork):
    codelists: SqlCodeListRepository
    conventions: SqlConventionsRepository

    def _start(self) -> None:
        self.codelists = SqlCodeListRepository(self.session, self)
        self.conventions = SqlConventionsRepository(self.session, self)
