"""What the intake context asks of the invoicing context (plan §4.7, §7.1): an uploaded
document becomes an invoice waiting for its extraction job, in the same transaction that
stores the document and queues the job; the job's outcome moves the invoice on."""

from riso.identity import Permission
from riso.invoicing.application.coding import actor_of
from riso.invoicing.application.uow import InvoicingUnitOfWork
from riso.invoicing.domain.invoice import Channel, Invoice
from riso.shared.context import RequestContext


def register_upload(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    customer_id: str,
    *,
    invoice_id: str,
    document_id: str,
    channel: str,
    job_id: str,
    source_ref: str | None = None,
) -> None:
    """The invoice of an uploaded document, already waiting for the job that reads it.
    Runs inside the caller's unit of work, which commits."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    actor = actor_of(ctx)
    at = uow.clock.now()
    invoice = Invoice.uploaded(
        invoice_id,
        customer_id,
        Channel(channel),
        document_id,
        at=at,
        actor=actor,
        source_ref=source_ref,
    )
    invoice.start_extraction(job_id, at, actor)
    uow.invoices.add(invoice)
    uow.audit.record(
        ctx,
        "invoice.uploaded",
        target_type="invoice",
        target_id=invoice_id,
        customer_id=customer_id,
        details={"document_id": document_id, "channel": channel, "job_id": job_id},
    )


def invoice_of_document(uow: InvoicingUnitOfWork, customer_id: str, document_id: str) -> str | None:
    """The ID of the invoice the document became; for the duplicate's link and the storage
    listing. The caller checked the permission."""
    invoice = uow.invoices.for_document(customer_id, document_id)
    return invoice.id if invoice else None


def fail_extraction(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    customer_id: str,
    invoice_id: str,
    job_id: str,
    reason: str,
) -> bool:
    """The job could not read the document: the invoice waits for manual entry or a retry
    with the reason. False, changing nothing, when the invoice no longer waits for this job
    (a retry ran it already), so the job stays idempotent. Inside the caller's unit of work."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    invoice = uow.invoices.get(customer_id, invoice_id)
    if not invoice.awaits(job_id):
        return False
    invoice.extraction_failed(reason, uow.clock.now(), actor_of(ctx))
    uow.invoices.save(invoice)
    return True
