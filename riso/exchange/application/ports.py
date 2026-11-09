"""Ports of the exchange context: what its use cases need from adapters and other contexts."""

from collections.abc import Sequence
from typing import Protocol

from riso.contracts import Counters, SupplierMemory
from riso.exchange.domain.bookings import BookingsPlan
from riso.exchange.domain.export import Cell, Column, ExportFormat
from riso.exchange.domain.table import ReadOptions, Workbook


class TableReader(Protocol):
    """Reads an import file (CSV, XLSX or XLS, recognised by content) into a workbook.
    Raises `ValidationFailed` for a file it cannot read."""

    def read(self, data: bytes, options: ReadOptions | None = None) -> Workbook: ...


class SupplierMemorySource(Protocol):
    """The customer's supplier memory."""

    def memory(self, customer_id: str) -> SupplierMemory: ...


class PrecedentSink(SupplierMemorySource, Protocol):
    """Where a past-bookings import and a customer copy go: the customer's supplier memory
    and number series (the invoicing context's, on the database since P2-M4-T02). It works
    in the unit of work that offers it, so its changes commit with the import or the copy."""

    def counters(self, customer_id: str) -> Counters: ...

    def add(self, customer_id: str, plan: BookingsPlan) -> None:
        """Adds the plan's new precedents, marks its numbers used and raises its counters.
        The plan was made against the current memory and counters, so applying it again
        after a retry finds its bookings present and adds nothing twice."""
        ...

    def copy_memory(self, source_id: str, target_id: str) -> int:
        """Gives the target the source's supplier memory (a customer copy) and returns how
        many suppliers it has. A target that has a memory already keeps it (0)."""
        ...


class CustomerDirectory(Protocol):
    def ico_of(self, customer_id: str) -> str:
        """The customer's IČO; raises `NotFound` for an unknown customer."""
        ...

    def provider_of(self, customer_id: str) -> str | None:
        """The service provider the customer is assigned to, if any."""
        ...


class ExportWriter(Protocol):
    """Writes an export's rows as a file of the format (plan §7.4)."""

    def write(
        self,
        export_format: ExportFormat,
        columns: Sequence[Column],
        rows: Sequence[Sequence[Cell]],
    ) -> bytes: ...
