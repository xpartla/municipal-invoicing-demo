"""Ports of the exchange context: what its use cases need from adapters and other contexts."""

from typing import Protocol

from riso.contracts import Counters, SupplierMemory
from riso.exchange.domain.bookings import BookingsPlan
from riso.exchange.domain.table import ReadOptions, Workbook


class TableReader(Protocol):
    """Reads an import file (CSV, XLSX or XLS, recognised by content) into a workbook.
    Raises `ValidationFailed` for a file it cannot read."""

    def read(self, data: bytes, options: ReadOptions | None = None) -> Workbook: ...


class SupplierMemorySource(Protocol):
    """The customer's supplier memory: the demo's files until P2-M4 moves it."""

    def memory(self, customer_id: str) -> SupplierMemory: ...


class PrecedentSink(SupplierMemorySource, Protocol):
    """Where a past-bookings import goes: the customer's supplier memory and counters. The
    first adapter writes the demo's files; P2-M4-T02 switches it to the database."""

    def counters(self, customer_id: str) -> Counters: ...

    def add(self, customer_id: str, plan: BookingsPlan) -> None:
        """Adds the plan's new precedents, marks its numbers used and raises its counters.
        The plan was made against the current memory and counters, so applying it again
        after a retry finds its bookings present and adds nothing twice."""
        ...


class CustomerDirectory(Protocol):
    def ico_of(self, customer_id: str) -> str:
        """The customer's IČO; raises `NotFound` for an unknown customer."""
        ...

    def provider_of(self, customer_id: str) -> str | None:
        """The service provider the customer is assigned to, if any."""
        ...
