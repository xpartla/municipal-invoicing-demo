"""The number series repository on SQLAlchemy, mapped explicitly.

Saving a series compares its holders with the stored rows by ID: removed ones are deleted,
moved ones updated highest first (a booking moves holders up by one, so each update lands
on a number its predecessor just left, and neither unique constraint is broken on the way),
then new ones inserted.
"""

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from riso.invoicing.domain.numbering import Holder, HolderKind, NumberSeries
from riso.invoicing.infrastructure.orm import NumberSeriesRow, UsedNumberRow
from riso.shared.errors import NotFound
from riso.shared.uow import UnitOfWork


def _holder(row: UsedNumberRow) -> Holder:
    assert row.sequence is not None
    return Holder(
        id=row.id,
        sequence=row.sequence,
        kind=HolderKind(row.kind),
        invoice_id=row.invoice_id,
        supply_date=row.supply_date,
        received_at=row.received_at,
        frozen=row.frozen,
        requested=row.requested_sequence,
    )


def _series(row: NumberSeriesRow, holders: list[Holder]) -> NumberSeries:
    return NumberSeries(
        id=row.id,
        customer_id=row.customer_id,
        series=row.series,
        year=row.year,
        pattern=row.pattern,
        last_used=row.last_used,
        updated_at=row.updated_at,
        holders=sorted(holders, key=lambda h: h.sequence),
    )


def _apply(row: UsedNumberRow, series: NumberSeries, holder: Holder) -> None:
    row.sequence = holder.sequence
    row.number = series.number(holder.sequence)
    row.kind = holder.kind.value
    row.invoice_id = holder.invoice_id
    row.supply_date = holder.supply_date
    row.received_at = holder.received_at
    row.frozen = holder.frozen
    row.requested_sequence = holder.requested


class SqlNumberSeriesRepository:
    def __init__(self, session: Session, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow

    def _load(self, rows: Iterable[NumberSeriesRow]) -> list[NumberSeries]:
        rows = list(rows)
        holders: defaultdict[str, list[Holder]] = defaultdict(list)
        if rows:
            for used in self._session.scalars(
                select(UsedNumberRow).where(UsedNumberRow.series_id.in_([r.id for r in rows]))
            ):
                assert used.series_id is not None
                holders[used.series_id].append(_holder(used))
        found = [_series(row, holders[row.id]) for row in rows]
        for series in found:
            self._uow.track(series)
        return found

    def find(self, customer_id: str, series: str, year: int) -> NumberSeries | None:
        row = self._session.scalar(
            select(NumberSeriesRow).where(
                NumberSeriesRow.customer_id == customer_id,
                NumberSeriesRow.series == series,
                NumberSeriesRow.year == year,
            )
        )
        return self._load([row])[0] if row else None

    def of_customer(self, customer_id: str, *, year: int | None = None) -> list[NumberSeries]:
        statement = select(NumberSeriesRow).where(NumberSeriesRow.customer_id == customer_id)
        if year is not None:
            statement = statement.where(NumberSeriesRow.year == year)
        return self._load(
            self._session.scalars(statement.order_by(NumberSeriesRow.year, NumberSeriesRow.series))
        )

    def holding(self, customer_id: str, invoice_id: str) -> list[NumberSeries]:
        ids = select(UsedNumberRow.series_id).where(
            UsedNumberRow.customer_id == customer_id, UsedNumberRow.invoice_id == invoice_id
        )
        return self._load(
            self._session.scalars(
                select(NumberSeriesRow)
                .where(NumberSeriesRow.customer_id == customer_id, NumberSeriesRow.id.in_(ids))
                .order_by(NumberSeriesRow.year, NumberSeriesRow.series)
            )
        )

    def add(self, series: NumberSeries) -> None:
        self._session.add(
            NumberSeriesRow(
                id=series.id,
                customer_id=series.customer_id,
                series=series.series,
                year=series.year,
                pattern=series.pattern,
                last_used=series.last_used,
                updated_at=series.updated_at,
            )
        )
        self._session.flush()
        self._save_holders(series)
        self._uow.track(series)

    def save(self, series: NumberSeries) -> None:
        row = self._session.scalar(
            select(NumberSeriesRow).where(
                NumberSeriesRow.id == series.id,
                NumberSeriesRow.customer_id == series.customer_id,
            )
        )
        if row is None:
            raise NotFound(f"no number series {series.id}")
        row.pattern, row.last_used, row.updated_at = (
            series.pattern,
            series.last_used,
            series.updated_at,
        )
        self._save_holders(series)
        self._uow.track(series)

    def _save_holders(self, series: NumberSeries) -> None:
        stored = {
            r.id: r
            for r in self._session.scalars(
                select(UsedNumberRow).where(UsedNumberRow.series_id == series.id)
            )
        }
        current = {h.id: h for h in series.holders}
        gone = [row_id for row_id in stored if row_id not in current]
        if gone:
            self._session.execute(delete(UsedNumberRow).where(UsedNumberRow.id.in_(gone)))
            for row_id in gone:
                self._session.expunge(stored.pop(row_id))
        kept = sorted((h for h in series.holders if h.id in stored), key=lambda h: -h.sequence)
        for holder in kept:
            row = stored[holder.id]
            if _holder(row) != holder:
                _apply(row, series, holder)
                self._session.flush()
        for holder in series.holders:
            if holder.id not in stored:
                row = UsedNumberRow(
                    id=holder.id, customer_id=series.customer_id, series_id=series.id
                )
                _apply(row, series, holder)
                self._session.add(row)
        self._session.flush()

    def used_numbers(self, customer_id: str) -> list[str]:
        return list(
            self._session.scalars(
                select(UsedNumberRow.number)
                .where(UsedNumberRow.customer_id == customer_id)
                .order_by(UsedNumberRow.id)
            )
        )

    def add_loose(self, customer_id: str, number: str) -> bool:
        exists = self._session.scalar(
            select(UsedNumberRow.id).where(
                UsedNumberRow.customer_id == customer_id, UsedNumberRow.number == number
            )
        )
        if exists is not None:
            return False
        self._session.add(
            UsedNumberRow(
                id=self._uow.ids.new(),
                customer_id=customer_id,
                series_id=None,
                sequence=None,
                number=number,
                kind=HolderKind.EXTERNAL.value,
                frozen=True,
                requested_sequence=None,
            )
        )
        self._session.flush()
        return True
