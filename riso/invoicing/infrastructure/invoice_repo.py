"""The invoice repository on SQLAlchemy, mapped explicitly.

Saving writes the aggregate's row with its denormalised columns, replaces its lines (the
booking's, else the proposal's) and appends the history entries recorded since it was
loaded.
"""

import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from riso.contracts import Coding, CodingProposal, InvoiceDocument
from riso.invoicing.domain.invoice import (
    Booking,
    Channel,
    CodingBasis,
    EventKind,
    Invoice,
    InvoiceEvent,
    InvoiceState,
)
from riso.invoicing.infrastructure.orm import InvoiceEventRow, InvoiceLineRow, InvoiceRow
from riso.shared.errors import NotFound
from riso.shared.uow import UnitOfWork
from riso.text import fold


def searchable(text: str) -> str:
    """Text as the search columns keep it: without diacritics, case folded (portable `LIKE`
    then ignores both, on SQLite and PostgreSQL alike)."""
    return fold(text).casefold()


def cents(amount: Decimal | None) -> int | None:
    if amount is None:
        return None
    return int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _ico(text: str | None) -> str | None:
    """The IČO as the table filters it: digits, the old short ones zero-padded."""
    digits = re.sub(r"\D", "", text or "")
    return digits.zfill(8) if 6 <= len(digits) <= 8 else None


def _booking_json(booking: Booking | None) -> dict[str, Any] | None:
    if booking is None:
        return None
    return {
        "coding": booking.coding.model_dump(mode="json"),
        "action": booking.action,
        "at": booking.at.isoformat(),
        "by": booking.by,
        "note": booking.note,
    }


def _booking(data: dict[str, Any] | None) -> Booking | None:
    if data is None:
        return None
    return Booking(
        coding=Coding.model_validate(data["coding"]),
        action=data["action"],
        at=datetime.fromisoformat(data["at"]),
        by=data["by"],
        note=data.get("note"),
    )


def _basis_json(basis: CodingBasis | None) -> dict[str, Any] | None:
    if basis is None:
        return None
    return {
        "year": basis.year,
        "bundle_id": basis.bundle_id,
        "version_ids": list(basis.version_ids),
        "conventions_revision": basis.conventions_revision,
    }


def _basis(data: dict[str, Any] | None) -> CodingBasis | None:
    if data is None:
        return None
    return CodingBasis(
        year=data["year"],
        bundle_id=data["bundle_id"],
        version_ids=tuple(data["version_ids"]),
        conventions_revision=data.get("conventions_revision"),
    )


def _coding(invoice: Invoice) -> Coding | None:
    """The coding the table shows: the booking's, else the proposal's."""
    if invoice.booking is not None:
        return invoice.booking.coding
    proposal = invoice.proposal
    if proposal is not None and proposal.posting and proposal.budget:
        return proposal.coding()
    return None


def _values(invoice: Invoice) -> dict[str, Any]:
    fields, proposal = invoice.fields, invoice.proposal
    document = (
        invoice.booking.coding.document
        if invoice.booking
        else (proposal.document if proposal else None)
    )
    header = fields.invoice if fields else None
    supplier_name = (proposal.supplier.name if proposal else None) or (
        fields.supplier.name if fields else None
    )
    supplier_ico = (proposal.supplier.ico if proposal else None) or _ico(
        fields.supplier.ico if fields else None
    )
    booking_date = (document.booking_date if document else None) or (
        fields.handwritten.date if fields else None
    )
    words = [
        supplier_name,
        supplier_ico,
        header.number if header else None,
        header.variable_symbol if header else None,
        document.number if document else None,
        invoice.source_ref,
    ]
    return {
        "customer_id": invoice.customer_id,
        "channel": invoice.channel.value,
        "state": invoice.state.value,
        "document_id": invoice.document_id,
        "source_ref": invoice.source_ref,
        "job_id": invoice.job_id,
        "fields": fields.model_dump(mode="json") if fields else None,
        "extraction_error": invoice.extraction_error,
        "duplicate_of": invoice.duplicate_of,
        "proposal": proposal.model_dump(mode="json") if proposal else None,
        "basis": _basis_json(invoice.basis),
        "coding_error": invoice.coding_error,
        "needs_review": invoice.needs_review,
        "booking": _booking_json(invoice.booking),
        "paid_on": invoice.paid_on,
        "discard_reason": invoice.discard_reason,
        "uploaded_at": invoice.uploaded_at,
        "uploaded_by": invoice.uploaded_by,
        "updated_at": invoice.updated_at,
        "checked_at": invoice.checked_at,
        "coded_at": invoice.coded_at,
        "booked_at": invoice.booked_at,
        "exported_at": invoice.exported_at,
        "paid_at": invoice.paid_at,
        "discarded_at": invoice.discarded_at,
        "supplier_ico": supplier_ico,
        "supplier_name": supplier_name,
        "invoice_number": header.number if header else None,
        "variable_symbol": header.variable_symbol if header else None,
        "issue_date": header.issue_date if header else None,
        "due_date": header.due_date if header else None,
        "supply_date": invoice.supply_date,
        "booking_date": booking_date,
        "series": document.series if document else None,
        "document_number": document.number if document else None,
        "gross_cents": cents(fields.totals.gross) if fields else None,
        "currency": header.currency if header else None,
        "search_text": searchable(" ".join(w for w in words if w)),
        "supplier_text": searchable(" ".join(w for w in (supplier_name, supplier_ico) if w)),
    }


def _invoice(row: InvoiceRow) -> Invoice:
    return Invoice(
        id=row.id,
        customer_id=row.customer_id,
        channel=Channel(row.channel),
        state=InvoiceState(row.state),
        uploaded_at=row.uploaded_at,
        uploaded_by=row.uploaded_by,
        updated_at=row.updated_at,
        document_id=row.document_id,
        source_ref=row.source_ref,
        job_id=row.job_id,
        fields=InvoiceDocument.model_validate(row.fields) if row.fields else None,
        extraction_error=row.extraction_error,
        duplicate_of=row.duplicate_of,
        proposal=CodingProposal.model_validate(row.proposal) if row.proposal else None,
        basis=_basis(row.basis),
        coding_error=row.coding_error,
        needs_review=row.needs_review,
        booking=_booking(row.booking),
        paid_on=row.paid_on,
        checked_at=row.checked_at,
        coded_at=row.coded_at,
        booked_at=row.booked_at,
        exported_at=row.exported_at,
        paid_at=row.paid_at,
        discarded_at=row.discarded_at,
        discard_reason=row.discard_reason,
    )


def history_entry(row: InvoiceEventRow) -> InvoiceEvent:
    return InvoiceEvent(
        invoice_id=row.invoice_id,
        customer_id=row.customer_id,
        kind=EventKind(row.kind),
        at=row.at,
        actor_id=row.actor_id,
        real_actor_id=row.real_actor_id,
        from_state=InvoiceState(row.from_state) if row.from_state else None,
        to_state=InvoiceState(row.to_state),
        details=row.details,
    )


class SqlInvoiceRepository:
    def __init__(self, session: Session, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow

    def add(self, invoice: Invoice) -> None:
        self._session.add(InvoiceRow(id=invoice.id, **_values(invoice)))
        self._session.flush()
        self._write_children(invoice)
        self._uow.track(invoice)

    def save(self, invoice: Invoice) -> None:
        row = self._row(invoice.customer_id, invoice.id)
        for name, value in _values(invoice).items():
            setattr(row, name, value)
        self._session.flush()
        self._write_children(invoice)
        self._uow.track(invoice)

    def _write_children(self, invoice: Invoice) -> None:
        self._session.execute(
            delete(InvoiceLineRow).where(
                InvoiceLineRow.customer_id == invoice.customer_id,
                InvoiceLineRow.invoice_id == invoice.id,
            )
        )
        coding = _coding(invoice)
        if coding is not None:
            for position, (post, budget) in enumerate(
                zip(coding.posting, coding.budget, strict=False)
            ):
                self._session.add(
                    InvoiceLineRow(
                        id=self._uow.ids.new(),
                        customer_id=invoice.customer_id,
                        invoice_id=invoice.id,
                        position=position,
                        budget_key=budget.key,
                        ek=budget.ek,
                        zdroj=budget.zdroj,
                        oddiel=budget.oddiel,
                        trieda=budget.trieda,
                        analytika=budget.analytika,
                        md=post.md,
                        dal=post.dal,
                        amount_cents=cents(budget.amount) or 0,
                    )
                )
        for event in invoice.history:
            self._session.add(
                InvoiceEventRow(
                    id=self._uow.ids.new(),
                    customer_id=event.customer_id,
                    invoice_id=event.invoice_id,
                    kind=event.kind.value,
                    at=event.at,
                    actor_id=event.actor_id,
                    real_actor_id=event.real_actor_id,
                    from_state=event.from_state.value if event.from_state else None,
                    to_state=event.to_state.value,
                    details=dict(event.details),
                )
            )
        invoice.history.clear()
        self._session.flush()

    def _row(self, customer_id: str, invoice_id: str) -> InvoiceRow:
        row = self._session.scalar(
            select(InvoiceRow).where(
                InvoiceRow.id == invoice_id, InvoiceRow.customer_id == customer_id
            )
        )
        if row is None:
            raise NotFound(f"no invoice {invoice_id}")
        return row

    def get(self, customer_id: str, invoice_id: str) -> Invoice:
        invoice = _invoice(self._row(customer_id, invoice_id))
        self._uow.track(invoice)
        return invoice

    def for_document(self, customer_id: str, document_id: str) -> Invoice | None:
        row = self._session.scalar(
            select(InvoiceRow).where(
                InvoiceRow.customer_id == customer_id, InvoiceRow.document_id == document_id
            )
        )
        if row is None:
            return None
        invoice = _invoice(row)
        self._uow.track(invoice)
        return invoice

    def history(self, customer_id: str, invoice_id: str) -> list[InvoiceEvent]:
        rows = self._session.scalars(
            select(InvoiceEventRow)
            .where(
                InvoiceEventRow.customer_id == customer_id,
                InvoiceEventRow.invoice_id == invoice_id,
            )
            # By ID (UUIDv7, strictly increasing per generator even when the clock steps
            # back), so the history is in the order it was written; `at` stays as recorded.
            .order_by(InvoiceEventRow.id)
        )
        return [history_entry(row) for row in rows]
