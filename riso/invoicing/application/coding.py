"""Coding a posted invoice with the customer's data (plan §4.3, P2-M2-T05).

Stateless: nothing is stored. The year is the invoice's booking year (the handwritten date,
else the issue date, else today; plan §6.6). The engine gets the customer's parameters of
that year as its entity context, the bundle of its active code list versions, the global
knowledge merged with its conventions, and its supplier memory and counters.

Until P2-M4 the memory and the counters come from the demo's files (`SupplierState`); the
rest comes from the database (`ReferenceData`).
"""

from datetime import date
from typing import Protocol

from riso.contracts import (
    CodingProposal,
    Counters,
    EntityContext,
    InvoiceDocument,
    ReferenceBundle,
    SupplierMemory,
)
from riso.engine import code_invoice
from riso.identity import Permission
from riso.knowledge import KnowledgeBase
from riso.shared.context import RequestContext


class ReferenceData(Protocol):
    """What the engine needs from the customer's settings, code lists and conventions."""

    def entity_context(self, ctx: RequestContext, customer_id: str, year: int) -> EntityContext:
        """Raises `InvalidState` when the customer has no parameters for the year."""
        ...

    def bundle(self, ctx: RequestContext, customer_id: str, year: int) -> ReferenceBundle:
        """Raises `InvalidState` when a list the engine needs is missing for the year."""
        ...

    def knowledge(self, ctx: RequestContext, customer_id: str, year: int) -> KnowledgeBase: ...


class SupplierState(Protocol):
    def memory(self, customer_id: str) -> SupplierMemory: ...

    def counters(self, customer_id: str) -> Counters: ...


def booking_year(document: InvoiceDocument, today: date) -> int:
    booked = document.handwritten.date or document.invoice.issue_date or today
    return booked.year


def code_document(
    ctx: RequestContext,
    reference: ReferenceData,
    state: SupplierState,
    customer_id: str,
    document: InvoiceDocument,
    *,
    today: date,
) -> CodingProposal:
    """The engine's proposal for the document, coded as the customer's invoice."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    year = booking_year(document, today)
    return code_invoice(
        document,
        entity=reference.entity_context(ctx, customer_id, year),
        bundle=reference.bundle(ctx, customer_id, year),
        memory=state.memory(customer_id),
        counters=state.counters(customer_id),
        knowledge=reference.knowledge(ctx, customer_id, year),
    )
