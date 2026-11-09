"""The invoicing repositories on the SQLAlchemy unit of work. The application's unit of work
(`riso.api.uow`) adds the ports: the series patterns from the code lists and the audit."""

from riso.invoicing.infrastructure.memory_repo import SqlSupplierMemoryRepository
from riso.invoicing.infrastructure.numbering_repo import SqlNumberSeriesRepository
from riso.platform.uow import SqlUnitOfWork


class SqlInvoicingUnitOfWork(SqlUnitOfWork):
    number_series: SqlNumberSeriesRepository
    supplier_memory: SqlSupplierMemoryRepository

    def _start(self) -> None:
        self.number_series = SqlNumberSeriesRepository(self.session, self)
        self.supplier_memory = SqlSupplierMemoryRepository(self.session, self)
