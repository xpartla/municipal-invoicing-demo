"""The supplier memory repository on SQLAlchemy: suppliers (in the order they were added),
their precedents (by position, 0 the newest) and the precedents' lines, read back as the
engine's `SupplierMemory` contract."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from riso.contracts import Precedent, SupplierMemory, SupplierRecord
from riso.invoicing.infrastructure.orm import PrecedentLineRow, PrecedentRow, SupplierRow
from riso.shared.uow import UnitOfWork


def _cents(amount: Decimal | None) -> int | None:
    return None if amount is None else int((amount * 100).to_integral_value())


def _amount(cents: int | None) -> Decimal | None:
    return None if cents is None else Decimal(cents).scaleb(-2)


class SqlSupplierMemoryRepository:
    def __init__(self, session: Session, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow

    def memory(self, customer_id: str, entity_ico: str) -> SupplierMemory:
        return SupplierMemory(entity_ico=entity_ico, suppliers=self._records(customer_id))

    def _records(self, customer_id: str) -> list[SupplierRecord]:
        suppliers = list(
            self._session.scalars(
                select(SupplierRow)
                .where(SupplierRow.customer_id == customer_id)
                .order_by(SupplierRow.id)
            )
        )
        precedents: defaultdict[str, list[PrecedentRow]] = defaultdict(list)
        for row in self._session.scalars(
            select(PrecedentRow)
            .where(PrecedentRow.customer_id == customer_id)
            .order_by(PrecedentRow.supplier_id, PrecedentRow.position, PrecedentRow.id)
        ):
            precedents[row.supplier_id].append(row)
        lines: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
        for line in self._session.scalars(
            select(PrecedentLineRow)
            .where(PrecedentLineRow.customer_id == customer_id)
            .order_by(PrecedentLineRow.precedent_id, PrecedentLineRow.position)
        ):
            lines[line.precedent_id].append(
                {
                    "budget_key": line.budget_key,
                    "md": line.md,
                    "dal": line.dal,
                    "budget_text": line.budget_text,
                    "posting_text": line.posting_text,
                }
            )
        return [
            SupplierRecord(
                ico=supplier.ico,
                name=supplier.name,
                precedents=[
                    Precedent.model_validate(
                        {
                            "document_number": p.document_number,
                            "booking_date": p.booking_date,
                            "amount": _amount(p.amount_cents),
                            "variable_symbol": p.variable_symbol,
                            "lines": lines[p.id],
                            "source": p.source,
                        }
                    )
                    for p in precedents[supplier.id]
                ],
            )
            for supplier in suppliers
            if precedents[supplier.id]
        ]

    def has_suppliers(self, customer_id: str) -> bool:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(SupplierRow)
                .where(SupplierRow.customer_id == customer_id)
            )
            or 0
        ) > 0

    def _supplier(self, customer_id: str, ico: str, name: str) -> SupplierRow:
        row = self._session.scalar(
            select(SupplierRow).where(
                SupplierRow.customer_id == customer_id, SupplierRow.ico == ico
            )
        )
        if row is None:
            row = SupplierRow(id=self._uow.ids.new(), customer_id=customer_id, ico=ico, name=name)
            self._session.add(row)
            self._session.flush()
        return row

    def _insert(
        self,
        customer_id: str,
        supplier_id: str,
        position: int,
        precedent: Precedent,
        invoice_id: str | None,
    ) -> None:
        row = PrecedentRow(
            id=self._uow.ids.new(),
            customer_id=customer_id,
            supplier_id=supplier_id,
            position=position,
            document_number=precedent.document_number,
            booking_date=precedent.booking_date,
            amount_cents=_cents(precedent.amount),
            variable_symbol=precedent.variable_symbol,
            source=precedent.source,
            invoice_id=invoice_id,
        )
        self._session.add(row)
        self._session.flush()  # before its lines: no relationship() orders the inserts
        for index, line in enumerate(precedent.lines):
            self._session.add(
                PrecedentLineRow(
                    id=self._uow.ids.new(),
                    customer_id=customer_id,
                    precedent_id=row.id,
                    position=index,
                    budget_key=line.budget_key,
                    md=line.md,
                    dal=line.dal,
                    budget_text=line.budget_text,
                    posting_text=line.posting_text,
                )
            )

    def add_precedent(
        self,
        customer_id: str,
        ico: str,
        name: str,
        precedent: Precedent,
        *,
        invoice_id: str | None = None,
    ) -> None:
        supplier = self._supplier(customer_id, ico, name)
        self._session.execute(
            update(PrecedentRow)
            .where(PrecedentRow.customer_id == customer_id, PrecedentRow.supplier_id == supplier.id)
            .values(position=PrecedentRow.position + 1)
        )
        self._insert(customer_id, supplier.id, 0, precedent, invoice_id)
        self._session.flush()

    def add_past(
        self, customer_id: str, ico: str, name: str, precedents: Sequence[Precedent]
    ) -> None:
        supplier = self._supplier(customer_id, ico, name)
        stored = list(
            self._session.scalars(
                select(PrecedentRow)
                .where(
                    PrecedentRow.customer_id == customer_id,
                    PrecedentRow.supplier_id == supplier.id,
                )
                .order_by(PrecedentRow.position, PrecedentRow.id)
            )
        )
        merged: list[tuple[date | None, PrecedentRow | Precedent]] = [
            *((row.booking_date, row) for row in stored),
            *((p.booking_date, p) for p in precedents),
        ]
        # Stable: precedents of one date keep their order; undated ones go last.
        merged.sort(key=lambda item: item[0] or date.min, reverse=True)
        for position, (_, item) in enumerate(merged):
            if isinstance(item, PrecedentRow):
                item.position = position
            else:
                self._insert(customer_id, supplier.id, position, item, None)
        self._session.flush()

    def remove_precedents_of(self, customer_id: str, invoice_id: str) -> int:
        rows = list(
            self._session.scalars(
                select(PrecedentRow).where(
                    PrecedentRow.customer_id == customer_id, PrecedentRow.invoice_id == invoice_id
                )
            )
        )
        if not rows:
            return 0
        suppliers = {row.supplier_id for row in rows}
        ids = [row.id for row in rows]
        for row in rows:
            self._session.expunge(row)
        self._session.execute(
            delete(PrecedentLineRow).where(PrecedentLineRow.precedent_id.in_(ids))
        )
        self._session.execute(delete(PrecedentRow).where(PrecedentRow.id.in_(ids)))
        for supplier_id in suppliers:
            left = self._session.scalar(
                select(func.count())
                .select_from(PrecedentRow)
                .where(PrecedentRow.supplier_id == supplier_id)
            )
            if not left:
                self._session.execute(delete(SupplierRow).where(SupplierRow.id == supplier_id))
        self._session.flush()
        return len(rows)

    def renumber(self, customer_id: str, invoice_id: str, number: str) -> int:
        result = self._session.execute(
            update(PrecedentRow)
            .where(PrecedentRow.customer_id == customer_id, PrecedentRow.invoice_id == invoice_id)
            .values(document_number=number)
        )
        self._session.flush()
        return int(getattr(result, "rowcount", 0) or 0)

    def copy(self, source_id: str, target_id: str) -> int:
        if self.has_suppliers(target_id):
            return 0
        records = self._records(source_id)
        for record in records:
            supplier = self._supplier(target_id, record.ico, record.name)
            for position, precedent in enumerate(record.precedents):
                self._insert(target_id, supplier.id, position, precedent, None)
        self._session.flush()
        return len(records)
