"""Ports of the exchange context: what its use cases need from adapters and other contexts."""

from typing import Protocol

from riso.contracts import SupplierMemory
from riso.exchange.domain.table import ReadOptions, Workbook


class TableReader(Protocol):
    """Reads an import file (CSV, XLSX or XLS, recognised by content) into a workbook.
    Raises `ValidationFailed` for a file it cannot read."""

    def read(self, data: bytes, options: ReadOptions | None = None) -> Workbook: ...


class SupplierMemorySource(Protocol):
    """The customer's supplier memory: the demo's files until P2-M4 moves it."""

    def memory(self, customer_id: str) -> SupplierMemory: ...


class CustomerIcos(Protocol):
    def ico_of(self, customer_id: str) -> str:
        """The customer's IČO; raises `NotFound` for an unknown customer."""
        ...
