"""Invoices from typed fields (plan §8.5, decision 45): manual entry, and the dataset's
invoices that `riso seed` gives Boldog. The invoice is created from the fields and checked at
once, so it is coded in the same transaction. The fields take the invoice's ID and say how
it came in (`intake`)."""

from riso.contracts import Intake, InvoiceDocument
from riso.identity import Permission
from riso.invoicing.application.coding import ReferenceData, actor_of, code_stored
from riso.invoicing.application.uow import InvoicingUnitOfWork
from riso.invoicing.application.views import InvoiceView
from riso.invoicing.domain.invoice import Channel, Invoice
from riso.shared.context import RequestContext
from riso.shared.errors import InvalidState


def enter_invoice(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    reference: ReferenceData,
    customer_id: str,
    fields: InvoiceDocument,
    *,
    channel: Channel = Channel.MANUAL,
    source_ref: str | None = None,
) -> InvoiceView:
    """A new invoice from typed fields, checked and coded."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    if channel.has_file:
        raise InvalidState(f"a {channel} invoice comes from an upload")
    actor = actor_of(ctx)
    with uow:
        at = uow.clock.now()
        invoice_id = uow.ids.new()
        typed = fields.model_copy(
            update={"id": invoice_id, "intake": Intake(channel=channel.value)}
        )
        invoice = Invoice.entered(
            invoice_id, customer_id, channel, typed, at=at, actor=actor, source_ref=source_ref
        )
        invoice.check(typed, at, actor)
        code_stored(ctx, uow, reference, invoice, actor)
        uow.invoices.add(invoice)
        uow.audit.record(
            ctx,
            "invoice.entered",
            target_type="invoice",
            target_id=invoice_id,
            customer_id=customer_id,
            details={"channel": channel.value, "state": invoice.state.value},
        )
        uow.commit()
    return InvoiceView.of(invoice)
