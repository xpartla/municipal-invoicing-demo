"""The repository protocols of the invoicing context. Every method takes the customer
(guide §6.4)."""

from collections.abc import Sequence
from typing import Protocol

from riso.contracts import Precedent, SupplierMemory
from riso.invoicing.domain.invoice import Invoice, InvoiceEvent
from riso.invoicing.domain.numbering import NumberSeries


class InvoiceRepository(Protocol):
    def add(self, invoice: Invoice) -> None: ...

    def save(self, invoice: Invoice) -> None:
        """Stores the invoice and the history entries it recorded since it was loaded."""
        ...

    def get(self, customer_id: str, invoice_id: str) -> Invoice:
        """Raises `NotFound` when the customer has no such invoice."""
        ...

    def history(self, customer_id: str, invoice_id: str) -> list[InvoiceEvent]:
        """The invoice's history, oldest first."""
        ...


class NumberSeriesRepository(Protocol):
    def find(self, customer_id: str, series: str, year: int) -> NumberSeries | None: ...

    def add(self, series: NumberSeries) -> None: ...

    def save(self, series: NumberSeries) -> None: ...

    def of_customer(self, customer_id: str, *, year: int | None = None) -> list[NumberSeries]:
        """The customer's series (of one year), by year and series code."""
        ...

    def holding(self, customer_id: str, invoice_id: str) -> list[NumberSeries]:
        """The series in which the invoice holds a number (booked or reserved)."""
        ...

    def used_numbers(self, customer_id: str) -> list[str]:
        """Every number the customer has used, in the order they were first used: those held
        in a series and those outside any (`add_loose`)."""
        ...

    def add_loose(self, customer_id: str, number: str) -> bool:
        """A used number that fits no series (an unknown series, or another pattern), kept so
        the engine still warns about it. False when it is used already."""
        ...


class SupplierMemoryRepository(Protocol):
    """The customer's supplier memory (plan §4.3): suppliers with their precedents, newest
    first, as the engine reads them."""

    def memory(self, customer_id: str, entity_ico: str) -> SupplierMemory: ...

    def has_suppliers(self, customer_id: str) -> bool: ...

    def add_precedent(
        self,
        customer_id: str,
        ico: str,
        name: str,
        precedent: Precedent,
        *,
        invoice_id: str | None = None,
    ) -> None:
        """The precedent becomes the supplier's newest (S8); a new supplier is added last."""
        ...

    def add_past(
        self, customer_id: str, ico: str, name: str, precedents: Sequence[Precedent]
    ) -> None:
        """Past bookings join the supplier's precedents, which are then ordered newest first
        by booking date; precedents of one date keep their order, undated ones go last."""
        ...

    def remove_precedents_of(self, customer_id: str, invoice_id: str) -> int:
        """Removes the precedents a booking of the invoice made (unbooking); a supplier left
        without precedents goes too."""
        ...

    def renumber(self, customer_id: str, invoice_id: str, number: str) -> int:
        """The booking's precedent follows its renumbered invoice."""
        ...

    def copy(self, source_id: str, target_id: str) -> int:
        """Gives the target the source's suppliers and precedents (a customer copy), without
        their links to the source's invoices. Returns how many suppliers were copied."""
        ...
