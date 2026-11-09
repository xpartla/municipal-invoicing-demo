"""The unit of work the invoicing use cases need, and its ports."""

from collections.abc import Mapping
from typing import Protocol

from riso.invoicing.domain.repository import NumberSeriesRepository, SupplierMemoryRepository
from riso.shared.ports import AuditRecorder
from riso.shared.uow import UnitOfWork


class SeriesPatterns(Protocol):
    def patterns(self, customer_id: str, year: int) -> Mapping[str, str]:
        """The customer's document series of the year, code → pattern (`FD` → `FD/XXX/RR`),
        from its active list; empty without one."""
        ...

    def invoice_series(self, customer_id: str, year: int) -> tuple[str, ...]:
        """The series the customer books supplier invoices in that year: its parameters'
        default and canteen series; empty without parameters."""
        ...


class InvoicingUnitOfWork(UnitOfWork, Protocol):
    @property
    def number_series(self) -> NumberSeriesRepository: ...

    @property
    def supplier_memory(self) -> SupplierMemoryRepository: ...

    @property
    def series_patterns(self) -> SeriesPatterns: ...

    @property
    def audit(self) -> AuditRecorder: ...
