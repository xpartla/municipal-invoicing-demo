"""The dashboards' reads on SQLAlchemy (plan §10.2, §10.8): the invoice facts of a period,
the booked amounts per budget key of a year, and the per-customer counts. Grouping by day
happens in Python, since a Bratislava day is not portable SQL; everything else is portable."""

from collections import defaultdict
from collections.abc import Collection
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from riso.invoicing.application.statistics import (
    BOOKED_STATES,
    CustomerCounts,
    InvoiceFact,
    LineFact,
)
from riso.invoicing.infrastructure.orm import InvoiceLineRow, InvoiceRow

_FACT_COLUMNS = (
    InvoiceRow.id,
    InvoiceRow.state,
    InvoiceRow.series,
    InvoiceRow.fields["invoice"]["document_type"].as_string(),
    InvoiceRow.gross_cents,
    InvoiceRow.supplier_ico,
    InvoiceRow.supplier_name,
    InvoiceRow.needs_review,
    InvoiceRow.uploaded_at,
    InvoiceRow.booked_at,
)


def _amount(cents: int) -> Decimal:
    return Decimal(cents).scaleb(-2)


def _fact(row: Any, lines: tuple[LineFact, ...] = ()) -> InvoiceFact:
    (id_, state, series, document_type, gross_cents, ico, name, review, uploaded, booked) = row
    gross = None if gross_cents is None else _amount(gross_cents)
    credit_note = document_type == "credit_note" or (gross is not None and gross < 0)
    if credit_note and gross is not None and gross > 0:
        gross = -gross
    return InvoiceFact(
        id=id_,
        state=state,
        series=series,
        credit_note=credit_note,
        gross=gross,
        supplier_ico=ico,
        supplier_name=name,
        needs_review=bool(review),
        uploaded_at=uploaded,
        booked_at=booked,
        lines=lines,
    )


def _booked() -> ColumnElement[bool]:
    return InvoiceRow.state.in_(BOOKED_STATES)


class SqlInvoiceStatistics:
    def __init__(self, session: Session) -> None:
        self._session = session

    def uploaded(self, customer_id: str, start: datetime, end: datetime) -> list[InvoiceFact]:
        rows = self._session.execute(
            select(*_FACT_COLUMNS)
            .where(
                InvoiceRow.customer_id == customer_id,
                InvoiceRow.uploaded_at >= start,
                InvoiceRow.uploaded_at < end,
            )
            .order_by(InvoiceRow.id)
        )
        return [_fact(r) for r in rows]

    def booked(
        self, customer_id: str, start: datetime, end: datetime, *, lines: bool = False
    ) -> list[InvoiceFact]:
        rows = list(
            self._session.execute(
                select(*_FACT_COLUMNS)
                .where(
                    InvoiceRow.customer_id == customer_id,
                    _booked(),
                    InvoiceRow.booked_at >= start,
                    InvoiceRow.booked_at < end,
                )
                .order_by(InvoiceRow.id)
            )
        )
        found: defaultdict[str, list[LineFact]] = defaultdict(list)
        if lines and rows:
            for invoice_id, oddiel, trieda, cents in self._session.execute(
                select(
                    InvoiceLineRow.invoice_id,
                    InvoiceLineRow.oddiel,
                    InvoiceLineRow.trieda,
                    InvoiceLineRow.amount_cents,
                )
                .where(
                    InvoiceLineRow.customer_id == customer_id,
                    InvoiceLineRow.invoice_id.in_([r[0] for r in rows]),
                )
                .order_by(InvoiceLineRow.invoice_id, InvoiceLineRow.position)
            ):
                found[invoice_id].append(LineFact(oddiel, trieda, _amount(cents)))
        return [_fact(r, tuple(found[r[0]])) for r in rows]

    def drawn(self, customer_id: str, year: int) -> dict[str, Decimal]:
        rows = self._session.execute(
            select(InvoiceLineRow.budget_key, func.sum(InvoiceLineRow.amount_cents))
            .join(InvoiceRow, InvoiceRow.id == InvoiceLineRow.invoice_id)
            .where(
                InvoiceLineRow.customer_id == customer_id,
                InvoiceRow.customer_id == customer_id,
                _booked(),
                InvoiceRow.booking_date >= date(year, 1, 1),
                InvoiceRow.booking_date <= date(year, 12, 31),
            )
            .group_by(InvoiceLineRow.budget_key)
        )
        return {key: _amount(int(total)) for key, total in rows}

    def any_booked(self, customer_id: str) -> bool:
        found = self._session.scalar(
            select(InvoiceRow.id).where(InvoiceRow.customer_id == customer_id, _booked()).limit(1)
        )
        return found is not None

    def counts(
        self, customer_ids: Collection[str], start: datetime, end: datetime
    ) -> dict[str, CustomerCounts]:
        ids = list(customer_ids)
        by_state: defaultdict[str, dict[str, int]] = defaultdict(dict)
        booked: dict[str, int] = {}
        if ids:
            for customer_id, state, count in self._session.execute(
                select(InvoiceRow.customer_id, InvoiceRow.state, func.count())
                .where(
                    InvoiceRow.customer_id.in_(ids),
                    InvoiceRow.uploaded_at >= start,
                    InvoiceRow.uploaded_at < end,
                )
                .group_by(InvoiceRow.customer_id, InvoiceRow.state)
            ):
                by_state[customer_id][state] = count
            for customer_id, count in self._session.execute(
                select(InvoiceRow.customer_id, func.count())
                .where(
                    InvoiceRow.customer_id.in_(ids),
                    _booked(),
                    InvoiceRow.booked_at >= start,
                    InvoiceRow.booked_at < end,
                )
                .group_by(InvoiceRow.customer_id)
            ):
                booked[customer_id] = count
        return {
            i: CustomerCounts(
                uploaded=sum(by_state[i].values()),
                by_state=dict(by_state[i]),
                booked=booked.get(i, 0),
            )
            for i in ids
        }

    def total_uploaded(self, start: datetime, end: datetime) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(InvoiceRow)
                .where(InvoiceRow.uploaded_at >= start, InvoiceRow.uploaded_at < end)
            )
            or 0
        )
