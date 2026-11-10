"""What an export reads from the invoices and what it records on them (plan §7.4). The export
itself (its run, its file, its job) is the exchange context's; it calls these in its own
unit of work."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from riso.contracts import Coding
from riso.identity import Permission
from riso.invoicing.application.coding import actor_of
from riso.invoicing.application.uow import InvoicingUnitOfWork
from riso.invoicing.domain.invoice import BOOKED_STATES
from riso.shared.context import RequestContext
from riso.shared.errors import NotFound


@dataclass(frozen=True, slots=True)
class ExportableInvoice:
    """A booked invoice as an export lays it out: the header and the booked coding."""

    id: str
    state: str
    exported_before: bool
    series: str
    number: str | None
    booking_date: date | None
    supplier_name: str | None
    supplier_ico: str | None
    invoice_number: str | None
    variable_symbol: str | None
    issue_date: date | None
    supply_date: date | None
    due_date: date | None
    gross: Decimal | None
    coding: Coding


def exportable(
    uow: InvoicingUnitOfWork, customer_id: str, invoice_ids: Sequence[str]
) -> tuple[list[ExportableInvoice], list[str]]:
    """The booked, exported and paid invoices among the IDs, in their order, and the IDs of
    the others (not booked, or not the customer's). Call inside the unit of work."""
    found, skipped = [], []
    for invoice_id in dict.fromkeys(invoice_ids):
        try:
            invoice = uow.invoices.get(customer_id, invoice_id)
        except NotFound:
            skipped.append(invoice_id)
            continue
        if invoice.state not in BOOKED_STATES or invoice.booking is None:
            skipped.append(invoice_id)
            continue
        fields, proposal = invoice.fields, invoice.proposal
        coding = invoice.booking.coding
        assert fields is not None
        found.append(
            ExportableInvoice(
                id=invoice.id,
                state=invoice.state.value,
                exported_before=invoice.exported_at is not None,
                series=coding.document.series,
                number=coding.document.number,
                booking_date=coding.document.booking_date,
                supplier_name=(proposal.supplier.name if proposal else None)
                or fields.supplier.name,
                supplier_ico=(proposal.supplier.ico if proposal else None) or fields.supplier.ico,
                invoice_number=fields.invoice.number,
                variable_symbol=fields.invoice.variable_symbol,
                issue_date=fields.invoice.issue_date,
                supply_date=invoice.supply_date,
                due_date=fields.invoice.due_date,
                gross=fields.totals.gross,
                coding=coding,
            )
        )
    return found, skipped


def record_exports(
    ctx: RequestContext,
    uow: InvoicingUnitOfWork,
    customer_id: str,
    invoice_ids: Sequence[str],
    export_run_id: str,
) -> int:
    """The invoices went into the export: booked ones become exported, exported and paid ones
    keep their state; each gets `exported_at` and a history entry, and its number never moves
    again (decision 61). Call inside the unit of work; returns how many had been exported
    before."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    actor, at, again = actor_of(ctx), uow.clock.now(), 0
    for invoice_id in invoice_ids:
        invoice = uow.invoices.get(customer_id, invoice_id)
        again += invoice.record_export(export_run_id, at, actor)
        uow.invoices.save(invoice)
        for series in uow.number_series.holding(customer_id, invoice_id):
            if series.freeze(invoice_id, at):
                uow.number_series.save(series)
    return again
