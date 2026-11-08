"""The tenancy unit of work on SQLAlchemy."""

from riso.platform.uow import SqlUnitOfWork
from riso.tenancy.infrastructure.repository import (
    SqlCustomerRepository,
    SqlParametersRepository,
    SqlProviderRepository,
)


class SqlTenancyUnitOfWork(SqlUnitOfWork):
    customers: SqlCustomerRepository
    providers: SqlProviderRepository
    parameters: SqlParametersRepository

    def _start(self) -> None:
        self.customers = SqlCustomerRepository(self.session, self)
        self.providers = SqlProviderRepository(self.session, self)
        self.parameters = SqlParametersRepository(self.session)
