"""The invoice table's queries on SQLAlchemy (plan §10.3): filters on the denormalised columns
and the lines, sorting with the ID as the tie-break, paging. Portable SQL only."""

from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from riso.invoicing.application.queries import (
    InvoiceFilter,
    InvoicePage,
    InvoiceRowView,
    Sort,
    SupplierView,
    day_end,
    day_start,
)
from riso.invoicing.infrastructure.invoice_repo import cents, searchable
from riso.invoicing.infrastructure.orm import InvoiceLineRow, InvoiceRow

_SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "state": InvoiceRow.state,
    "document_number": InvoiceRow.document_number,
    "booking_date": InvoiceRow.booking_date,
    "supplier_name": InvoiceRow.supplier_name,
    "supplier_ico": InvoiceRow.supplier_ico,
    "invoice_number": InvoiceRow.invoice_number,
    "variable_symbol": InvoiceRow.variable_symbol,
    "issue_date": InvoiceRow.issue_date,
    "due_date": InvoiceRow.due_date,
    "supply_date": InvoiceRow.supply_date,
    "gross": InvoiceRow.gross_cents,
    "uploaded_at": InvoiceRow.uploaded_at,
    "exported_at": InvoiceRow.exported_at,
    "paid_on": InvoiceRow.paid_on,
}


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _prefix(column: InstrumentedAttribute[str], value: str) -> ColumnElement[bool]:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.like(f"{escaped}%", escape="\\")


def _conditions(customer_id: str, f: InvoiceFilter) -> list[ColumnElement[bool]]:
    found: list[ColumnElement[bool]] = [InvoiceRow.customer_id == customer_id]
    if f.text:
        for word in searchable(f.text).split():
            found.append(InvoiceRow.search_text.like(_like(word), escape="\\"))
    if f.supplier_ico:
        found.append(InvoiceRow.supplier_ico == f.supplier_ico)
    if f.states:
        found.append(InvoiceRow.state.in_(list(f.states)))
    if f.series:
        found.append(InvoiceRow.series.in_(list(f.series)))
    if f.channels:
        found.append(InvoiceRow.channel.in_(list(f.channels)))
    if f.needs_review is not None:
        found.append(InvoiceRow.needs_review == f.needs_review)
    if f.uploaded_by:
        found.append(InvoiceRow.uploaded_by == f.uploaded_by)
    for column, start, end in (
        (InvoiceRow.issue_date, f.issue_from, f.issue_to),
        (InvoiceRow.due_date, f.due_from, f.due_to),
        (InvoiceRow.booking_date, f.booking_from, f.booking_to),
        (InvoiceRow.paid_on, f.paid_from, f.paid_to),
    ):
        if start is not None:
            found.append(column >= start)
        if end is not None:
            found.append(column <= end)
    for instant, start, end in (
        (InvoiceRow.uploaded_at, f.uploaded_from, f.uploaded_to),
        (InvoiceRow.exported_at, f.exported_from, f.exported_to),
        (InvoiceRow.booked_at, f.booked_from, f.booked_to),
    ):
        if start is not None:
            found.append(instant >= day_start(start))
        if end is not None:
            found.append(instant < day_end(end))
    if f.amount_min is not None:
        found.append(InvoiceRow.gross_cents >= cents(f.amount_min))
    if f.amount_max is not None:
        found.append(InvoiceRow.gross_cents <= cents(f.amount_max))
    lines = []
    if f.budget:
        lines.append(_prefix(InvoiceLineRow.budget_key, f.budget.strip()))
    if f.md:
        lines.append(_prefix(InvoiceLineRow.md, f.md.strip()))
    if f.dal:
        lines.append(_prefix(InvoiceLineRow.dal, f.dal.strip()))
    if lines:
        found.append(
            InvoiceRow.id.in_(
                select(InvoiceLineRow.invoice_id).where(
                    InvoiceLineRow.customer_id == customer_id, and_(*lines)
                )
            )
        )
    return found


def _ordered(statement: Select[Any], sort: Sort) -> Select[Any]:
    column = _SORT_COLUMNS[sort.key]
    # Empty values last in either direction, then the ID for a stable order.
    order = column.desc() if sort.descending else column.asc()
    tie = InvoiceRow.id.desc() if sort.descending else InvoiceRow.id.asc()
    return statement.order_by(column.is_(None), order, tie)


def _amount(value: int | None) -> Decimal | None:
    return None if value is None else Decimal(value).scaleb(-2)


class SqlInvoiceQueries:
    def __init__(self, session: Session) -> None:
        self._session = session

    def page(
        self,
        customer_id: str,
        criteria: InvoiceFilter,
        sort: Sort,
        *,
        offset: int,
        limit: int,
    ) -> InvoicePage:
        where = _conditions(customer_id, criteria)
        total = self._session.scalar(select(func.count()).select_from(InvoiceRow).where(*where))
        rows = list(
            self._session.scalars(
                _ordered(select(InvoiceRow).where(*where), sort).offset(offset).limit(limit)
            )
        )
        lines: defaultdict[str, list[InvoiceLineRow]] = defaultdict(list)
        if rows:
            for line in self._session.scalars(
                select(InvoiceLineRow)
                .where(
                    InvoiceLineRow.customer_id == customer_id,
                    InvoiceLineRow.invoice_id.in_([r.id for r in rows]),
                )
                .order_by(InvoiceLineRow.invoice_id, InvoiceLineRow.position)
            ):
                lines[line.invoice_id].append(line)
        return InvoicePage(
            [
                InvoiceRowView(
                    id=r.id,
                    state=r.state,
                    channel=r.channel,
                    source_ref=r.source_ref,
                    needs_review=r.needs_review,
                    series=r.series,
                    document_number=r.document_number,
                    booking_date=r.booking_date,
                    supplier_name=r.supplier_name,
                    supplier_ico=r.supplier_ico,
                    invoice_number=r.invoice_number,
                    variable_symbol=r.variable_symbol,
                    issue_date=r.issue_date,
                    due_date=r.due_date,
                    supply_date=r.supply_date,
                    gross=_amount(r.gross_cents),
                    currency=r.currency,
                    uploaded_at=r.uploaded_at,
                    uploaded_by=r.uploaded_by,
                    exported_at=r.exported_at,
                    paid_on=r.paid_on,
                    budget_keys=tuple(line.budget_key for line in lines[r.id]),
                    md=tuple(dict.fromkeys(line.md for line in lines[r.id])),
                    dal=tuple(dict.fromkeys(line.dal for line in lines[r.id])),
                )
                for r in rows
            ],
            total or 0,
        )

    def ids(self, customer_id: str, criteria: InvoiceFilter, sort: Sort) -> list[str]:
        statement = select(InvoiceRow.id).where(*_conditions(customer_id, criteria))
        return list(self._session.scalars(_ordered(statement, sort)))

    def suppliers(self, customer_id: str, text: str | None, *, limit: int) -> list[SupplierView]:
        statement = select(
            InvoiceRow.supplier_ico, func.max(InvoiceRow.supplier_name), func.count()
        ).where(InvoiceRow.customer_id == customer_id)
        for word in searchable(text or "").split():
            statement = statement.where(InvoiceRow.supplier_text.like(_like(word), escape="\\"))
        rows = self._session.execute(
            statement.group_by(InvoiceRow.supplier_ico)
            .order_by(func.count().desc(), func.max(InvoiceRow.supplier_name))
            .limit(limit)
        )
        return [SupplierView(ico, name, count) for ico, name, count in rows]
