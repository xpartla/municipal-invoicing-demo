"""The code list repository on SQLAlchemy, mapped explicitly: one mapping per kind turns an
entry into its table's row and back."""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, and_, insert, select, update
from sqlalchemy.orm import Session

from riso.codelists.domain import (
    AccountEntry,
    BudgetEntry,
    CodeListVersion,
    CofogEntry,
    CostCentreEntry,
    EkEntry,
    Entry,
    FrameworkAccountEntry,
    FundingSourceEntry,
    ListKind,
    ListWarning,
    SeriesEntry,
    SourceRef,
    TransferEntry,
    VersionInfo,
    VersionOrigin,
    VersionStatus,
)
from riso.codelists.infrastructure.orm import (
    AccountRow,
    BudgetPositionRow,
    CodeListVersionRow,
    CofogFunctionRow,
    CostCentreRow,
    DocumentSeriesRow,
    EkCodeRow,
    FrameworkAccountRow,
    FundingSourceRow,
    TransferRow,
)
from riso.shared.errors import NotFound
from riso.shared.uow import UnitOfWork

CENTS = Decimal(100)


def _cents(amount: Decimal | None) -> int | None:
    return None if amount is None else int(amount * CENTS)


def _amount(cents: int | None) -> Decimal | None:
    return None if cents is None else (Decimal(cents) / CENTS).quantize(Decimal("0.01"))


@dataclass(frozen=True, slots=True)
class _Mapping:
    row: Any
    """The ORM class."""
    to_row: Callable[[Any], dict[str, Any]]
    """The entry's own columns."""
    to_entry: Callable[[Any], Entry]


def _account_row(e: AccountEntry) -> dict[str, Any]:
    return {
        "su": e.su,
        "au": e.au,
        "type": e.type,
        "activity": e.activity,
        "description": e.description,
        "row": e.row,
    }


def _account(r: AccountRow) -> Entry:
    return AccountEntry(
        su=r.su,
        au=r.au,
        type=r.type,  # type: ignore[arg-type]  # stored from the AccountType literal
        activity=r.activity,
        description=r.description,
        row=r.row,
        active=r.active,
    )


def _budget_row(direction: str) -> Callable[[BudgetEntry], dict[str, Any]]:
    def to_row(e: BudgetEntry) -> dict[str, Any]:
        return {
            "direction": direction,
            "ek": e.ek,
            "zdroj": e.zdroj,
            "oddiel": e.oddiel,
            "trieda": e.trieda,
            "analytika": e.analytika,
            "description": e.description,
            "aliases": list(e.aliases),
            "rows": list(e.rows),
            "approved_cents": _cents(e.approved),
            "adjusted_cents": _cents(e.adjusted),
        }

    return to_row


def _budget(r: BudgetPositionRow) -> Entry:
    return BudgetEntry(
        ek=r.ek,
        zdroj=r.zdroj,
        analytika=r.analytika,
        oddiel=r.oddiel,
        trieda=r.trieda,
        description=r.description,
        aliases=tuple(r.aliases),
        rows=tuple(r.rows),
        approved=_amount(r.approved_cents),
        adjusted=_amount(r.adjusted_cents),
        active=r.active,
    )


def _series_row(e: SeriesEntry) -> dict[str, Any]:
    return {
        "series_id": e.series_id,
        "pattern": e.pattern,
        "description": e.description,
        "bank_account": e.bank_account,
    }


def _series(r: DocumentSeriesRow) -> Entry:
    return SeriesEntry(
        code=r.entry_key,
        series_id=r.series_id,
        pattern=r.pattern,
        description=r.description,
        bank_account=r.bank_account,
        active=r.active,
    )


def _transfer_row(e: TransferEntry) -> dict[str, Any]:
    return {"name": e.name, "zdroj": e.zdroj, "mock": e.mock}


def _transfer(r: TransferRow) -> Entry:
    return TransferEntry(id=r.entry_key, name=r.name, zdroj=r.zdroj, mock=r.mock, active=r.active)


def _named_row(e: CostCentreEntry | EkEntry | CofogEntry | FundingSourceEntry) -> dict[str, Any]:
    return {"name": e.name}


def _named(entry_type: type[Any]) -> Callable[[Any], Entry]:
    def to_entry(r: Any) -> Entry:
        entry: Entry = entry_type(r.entry_key, r.name, r.active)
        return entry

    return to_entry


MAPPINGS: dict[ListKind, _Mapping] = {
    ListKind.ACCOUNTS: _Mapping(AccountRow, _account_row, _account),
    ListKind.BUDGET_EXPENSE: _Mapping(BudgetPositionRow, _budget_row("expense"), _budget),
    ListKind.BUDGET_INCOME: _Mapping(BudgetPositionRow, _budget_row("income"), _budget),
    ListKind.DOCUMENT_SERIES: _Mapping(DocumentSeriesRow, _series_row, _series),
    ListKind.TRANSFERS: _Mapping(TransferRow, _transfer_row, _transfer),
    ListKind.COST_CENTRES: _Mapping(CostCentreRow, _named_row, _named(CostCentreEntry)),
    ListKind.EK: _Mapping(EkCodeRow, _named_row, _named(EkEntry)),
    ListKind.COFOG: _Mapping(CofogFunctionRow, _named_row, _named(CofogEntry)),
    ListKind.FUNDING_SOURCES: _Mapping(FundingSourceRow, _named_row, _named(FundingSourceEntry)),
    ListKind.FRAMEWORK_ACCOUNTS: _Mapping(
        FrameworkAccountRow, _named_row, _named(FrameworkAccountEntry)
    ),
}


def _owned_by(customer_id: str | None) -> ColumnElement[bool]:
    column = CodeListVersionRow.customer_id
    return column.is_(None) if customer_id is None else column == customer_id


def _info(row: CodeListVersionRow) -> VersionInfo:
    return VersionInfo(
        id=row.id,
        kind=ListKind(row.kind),
        customer_id=row.customer_id,
        year=row.year,
        number=row.number,
        status=VersionStatus(row.status),
        origin=VersionOrigin(row.origin),
        created_at=row.created_at,
        created_by=row.created_by,
        entry_count=row.entry_count,
        period=row.period,
        import_run_id=row.import_run_id,
        note=row.note,
    )


class SqlCodeListRepository:
    def __init__(self, session: Session, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow

    def add(self, version: CodeListVersion) -> None:
        source = version.source
        self._session.add(
            CodeListVersionRow(
                id=version.id,
                kind=version.kind.value,
                customer_id=version.customer_id,
                year=version.year,
                number=version.number,
                status=version.status.value,
                origin=version.origin.value,
                created_at=version.created_at,
                created_by=version.created_by,
                entry_count=len(version.entries),
                period=version.period,
                source_name=source.name if source else None,
                source_sha256=source.sha256 if source else None,
                source_rows=source.data_rows if source else None,
                warnings=[
                    {"code": w.code, "source": w.source, "rows": list(w.rows), "message": w.message}
                    for w in version.warnings
                ],
                import_run_id=version.import_run_id,
                note=version.note,
            )
        )
        self._session.flush()  # the entries refer to it
        mapping = MAPPINGS[version.kind]
        owner = {} if version.kind.is_global else {"customer_id": version.customer_id}
        rows = [
            {
                "version_id": version.id,
                "position": position,
                "entry_key": entry.key,
                "active": entry.active,
                **owner,
                **mapping.to_row(entry),
            }
            for position, entry in enumerate(version.entries)
        ]
        if rows:
            self._session.execute(insert(mapping.row), rows)
        self._uow.track(version)

    def save(self, version: CodeListVersion) -> None:
        result = self._session.execute(
            update(CodeListVersionRow)
            .where(CodeListVersionRow.id == version.id, _owned_by(version.customer_id))
            .values(status=version.status.value)
        )
        if result.rowcount == 0:  # type: ignore[attr-defined]  # a CursorResult for UPDATE
            raise NotFound(f"no code list version {version.id}")

    def _row(self, customer_id: str | None, version_id: str) -> CodeListVersionRow:
        row = self._session.scalars(
            select(CodeListVersionRow).where(
                CodeListVersionRow.id == version_id, _owned_by(customer_id)
            )
        ).first()
        if row is None:
            raise NotFound(f"no code list version {version_id}")
        return row

    def _read(self, row: CodeListVersionRow) -> CodeListVersion:
        kind = ListKind(row.kind)
        mapping = MAPPINGS[kind]
        table = mapping.row
        entries = tuple(
            mapping.to_entry(r)
            for r in self._session.scalars(
                select(table).where(table.version_id == row.id).order_by(table.position)
            )
        )
        source = (
            SourceRef(row.source_name, row.source_sha256 or "", row.source_rows or 0)
            if row.source_name is not None
            else None
        )
        version = CodeListVersion(
            id=row.id,
            kind=kind,
            customer_id=row.customer_id,
            year=row.year,
            number=row.number,
            status=VersionStatus(row.status),
            origin=VersionOrigin(row.origin),
            created_at=row.created_at,
            created_by=row.created_by,
            entries=entries,
            period=row.period,
            source=source,
            warnings=tuple(
                ListWarning(w["code"], w["source"], tuple(w["rows"]), w["message"])
                for w in row.warnings
            ),
            import_run_id=row.import_run_id,
            note=row.note,
        )
        self._uow.track(version)
        return version

    def get(self, customer_id: str | None, version_id: str) -> CodeListVersion:
        return self._read(self._row(customer_id, version_id))

    def active(self, customer_id: str | None, kind: ListKind, year: int) -> CodeListVersion | None:
        row = self._session.scalars(
            select(CodeListVersionRow).where(
                _owned_by(customer_id),
                and_(
                    CodeListVersionRow.kind == kind.value,
                    CodeListVersionRow.year == year,
                    CodeListVersionRow.status == VersionStatus.ACTIVE.value,
                ),
            )
        ).first()
        return None if row is None else self._read(row)

    def active_ids(self, customer_id: str | None, year: int) -> dict[ListKind, str]:
        rows = self._session.execute(
            select(CodeListVersionRow.kind, CodeListVersionRow.id).where(
                _owned_by(customer_id),
                CodeListVersionRow.year == year,
                CodeListVersionRow.status == VersionStatus.ACTIVE.value,
            )
        )
        return {ListKind(kind): version_id for kind, version_id in rows}

    def history(self, customer_id: str | None, kind: ListKind, year: int) -> list[VersionInfo]:
        rows = self._session.scalars(
            select(CodeListVersionRow)
            .where(
                _owned_by(customer_id),
                CodeListVersionRow.kind == kind.value,
                CodeListVersionRow.year == year,
            )
            .order_by(CodeListVersionRow.number.desc())
        )
        return [_info(row) for row in rows]

    def years(self, customer_id: str | None) -> list[int]:
        return list(
            self._session.scalars(
                select(CodeListVersionRow.year)
                .where(_owned_by(customer_id))
                .distinct()
                .order_by(CodeListVersionRow.year)
            )
        )
