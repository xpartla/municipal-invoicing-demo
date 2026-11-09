"""Coding invoices with the customer's data (plan §4.3, §7.1).

The year is the invoice's booking year (the handwritten date, else the issue date, else
today; plan §6.6). The engine gets the customer's parameters of that year as its entity
context, the bundle of its active code list versions, the global knowledge merged with its
conventions (`ReferenceData`), and its supplier memory and counters.

- `code_document` codes a posted invoice and stores nothing (P2-M2-T05).
- `check_invoice` stores the checked fields and codes them; `recode_invoice` codes them again
  with today's lists and memory (P2-M4-T03). A coding that cannot run (no lists for the
  year) leaves a checked invoice checked, with the reason.
- `line_for` derives the whole line a budget position brings, for the correction editors.

The invoice's own reserved number (decision 62) is not "used" for its own coding.
"""

from datetime import date
from typing import Protocol

from riso.contracts import (
    Alternative,
    CodingProposal,
    Counters,
    EntityContext,
    InvoiceDocument,
    ReferenceBundle,
    SupplierMemory,
)
from riso.engine import code_invoice, code_line
from riso.identity import Permission
from riso.invoicing.application.state import counters as stored_counters
from riso.invoicing.application.uow import InvoicingUnitOfWork
from riso.invoicing.application.views import InvoiceView
from riso.invoicing.domain.invoice import Actor, CodingBasis, Invoice, InvoiceState
from riso.knowledge import KnowledgeBase
from riso.shared.clock import local_date
from riso.shared.context import RequestContext
from riso.shared.errors import InvalidState, NotFound


class ReferenceData(Protocol):
    """What the engine needs from the customer's settings, code lists and conventions."""

    def entity_context(self, ctx: RequestContext, customer_id: str, year: int) -> EntityContext:
        """Raises `InvalidState` when the customer has no parameters for the year."""
        ...

    def bundle(self, ctx: RequestContext, customer_id: str, year: int) -> ReferenceBundle:
        """Raises `InvalidState` when a list the engine needs is missing for the year."""
        ...

    def knowledge(self, ctx: RequestContext, customer_id: str, year: int) -> KnowledgeBase: ...

    def basis(
        self, ctx: RequestContext, customer_id: str, year: int
    ) -> tuple[tuple[str, ...], int]:
        """What a coding of the year uses: the IDs of the customer's active code list
        versions and the revision of its conventions (0 for none)."""
        ...


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
    entity, bundle = _setting(ctx, reference, customer_id, year)
    return code_invoice(
        document,
        entity=entity,
        bundle=bundle,
        memory=state.memory(customer_id),
        counters=state.counters(customer_id),
        knowledge=reference.knowledge(ctx, customer_id, year),
    )


def _setting(
    ctx: RequestContext, reference: ReferenceData, customer_id: str, year: int
) -> tuple[EntityContext, ReferenceBundle]:
    """The customer's parameters and lists of the year. Raises `InvalidState` when a series
    the parameters name (default, canteen) is not in the document series list: the list can
    change after the parameters are set, and the engine needs the series' pattern."""
    entity = reference.entity_context(ctx, customer_id, year)
    bundle = reference.bundle(ctx, customer_id, year)
    known = {series.code for series in bundle.document_series}
    unknown = [
        s for s in dict.fromkeys((entity.default_series, entity.canteen_series)) if s not in known
    ]
    if unknown:
        raise InvalidState(
            f"the parameters of {year} name the series {', '.join(unknown)}, which the "
            "document series list does not have"
        )
    return entity, bundle


def actor_of(ctx: RequestContext) -> Actor:
    return Actor(ctx.actor_id, ctx.real_actor_id)


def _counters(uow: InvoicingUnitOfWork, customer_id: str, ico: str, invoice_id: str) -> Counters:
    """The counters, without the numbers the invoice itself holds (its reservation)."""
    counters = stored_counters(uow, customer_id, ico)
    own = {
        series.number(h.sequence)
        for series in uow.number_series.holding(customer_id, invoice_id)
        for h in series.holders
        if h.invoice_id == invoice_id
    }
    if not own:
        return counters
    return counters.model_copy(
        update={"used_numbers": [n for n in counters.used_numbers if n not in own]}
    )


def code_stored(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    reference: ReferenceData,
    invoice: Invoice,
    actor: Actor,
) -> None:
    """Codes the invoice's checked fields in the open unit of work."""
    assert invoice.fields is not None
    customer_id, at = invoice.customer_id, uow.clock.now()
    year = booking_year(invoice.fields, local_date(at))
    try:
        entity, bundle = _setting(ctx, reference, customer_id, year)
        knowledge = reference.knowledge(ctx, customer_id, year)
        versions, revision = reference.basis(ctx, customer_id, year)
    except InvalidState as exc:
        if invoice.state is not InvoiceState.CHECKED:
            raise
        invoice.coding_failed(exc.message, at)
        return
    proposal = code_invoice(
        invoice.fields,
        entity=entity,
        bundle=bundle,
        memory=uow.supplier_memory.memory(customer_id, entity.ico),
        counters=_counters(uow, customer_id, entity.ico, invoice.id),
        knowledge=knowledge,
    )
    invoice.record_coding(
        proposal, CodingBasis(year, bundle.bundle_id, versions, revision), at, actor
    )


def check_invoice(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    reference: ReferenceData,
    customer_id: str,
    invoice_id: str,
    fields: InvoiceDocument,
) -> InvoiceView:
    """The user confirms the fields (plan §8.5): they are stored, the invoice becomes
    checked and is coded. The fields take the invoice's ID."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    actor = actor_of(ctx)
    with uow:
        invoice = uow.invoices.get(customer_id, invoice_id)
        invoice.check(fields.model_copy(update={"id": invoice.id}), uow.clock.now(), actor)
        code_stored(ctx, uow, reference, invoice, actor)
        uow.invoices.save(invoice)
        uow.audit.record(
            ctx,
            "invoice.checked",
            target_type="invoice",
            target_id=invoice.id,
            customer_id=customer_id,
            details={"state": invoice.state.value},
        )
        uow.commit()
    return InvoiceView.of(invoice)


def recode_invoice(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    reference: ReferenceData,
    customer_id: str,
    invoice_id: str,
) -> InvoiceView:
    """Codes the checked fields again, with today's lists, conventions and memory."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    actor = actor_of(ctx)
    with uow:
        invoice = uow.invoices.get(customer_id, invoice_id)
        if invoice.fields is None or invoice.state not in (
            InvoiceState.CHECKED,
            InvoiceState.NEEDS_REVIEW,
            InvoiceState.READY,
        ):
            raise InvalidState(f"invoice {invoice_id} is {invoice.state}; it cannot be coded")
        code_stored(ctx, uow, reference, invoice, actor)
        uow.invoices.save(invoice)
        uow.audit.record(
            ctx,
            "invoice.recoded",
            target_type="invoice",
            target_id=invoice.id,
            customer_id=customer_id,
            details={"state": invoice.state.value},
        )
        uow.commit()
    return InvoiceView.of(invoice)


def line_for(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    reference: ReferenceData,
    customer_id: str,
    invoice_id: str,
    budget_key: str,
) -> Alternative:
    """The whole line (MD, DAL, transfer, texts) a budget position the user picked brings
    for this invoice, as S5 derives it. `NotFound` for a position outside the budget."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    with uow:
        invoice = uow.invoices.get(customer_id, invoice_id)
        if invoice.fields is None:
            raise InvalidState(f"invoice {invoice_id} has no fields yet")
        year = (
            invoice.basis.year
            if invoice.basis
            else booking_year(invoice.fields, local_date(uow.clock.now()))
        )
        entity = reference.entity_context(ctx, customer_id, year)
        memory = uow.supplier_memory.memory(customer_id, entity.ico)
        counters = _counters(uow, customer_id, entity.ico, invoice.id)
    try:
        return code_line(
            invoice.fields,
            budget_key,
            entity=entity,
            bundle=reference.bundle(ctx, customer_id, year),
            memory=memory,
            counters=counters,
            knowledge=reference.knowledge(ctx, customer_id, year),
        )
    except KeyError as exc:
        raise NotFound(f"{budget_key} is not in the {year} budget") from exc
