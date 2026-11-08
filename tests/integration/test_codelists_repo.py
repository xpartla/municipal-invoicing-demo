"""The code list repository: round trips on a migrated SQLite file, with the in-memory fake
run through the same tests so the two cannot drift."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from riso.codelists.domain import (
    AccountEntry,
    BudgetEntry,
    CodeListVersion,
    CofogEntry,
    CostCentreEntry,
    EkEntry,
    FrameworkAccountEntry,
    FundingSourceEntry,
    ListKind,
    ListWarning,
    SeriesEntry,
    SourceRef,
    TransferEntry,
    VersionOrigin,
    VersionStatus,
)
from riso.codelists.infrastructure.orm import AccountRow, CodeListVersionRow
from riso.codelists.infrastructure.uow import SqlCodelistsUnitOfWork
from riso.shared import FixedClock, Ico, NotFound, UuidV7Generator
from riso.tenancy.domain import Customer
from riso.tenancy.infrastructure.uow import SqlTenancyUnitOfWork
from tests.fakes.codelists import InMemoryCodelistsUnitOfWork

T0 = datetime(2026, 11, 8, 8, 0, tzinfo=UTC)

ENTRIES = {
    ListKind.ACCOUNTS: [
        AccountEntry("518", "003", "cost", description="telekom", row=12),
        AccountEntry("321", "000", "passive", activity="x", active=False),
    ],
    ListKind.BUDGET_EXPENSE: [
        BudgetEntry(
            ek="632005",
            zdroj="41",
            analytika="000",
            oddiel="01",
            trieda="110",
            description="telefon,fax",
            aliases=("telefón",),
            rows=(7, 8),
            approved=Decimal("1200.50"),
            adjusted=Decimal("-3.00"),
        ),
    ],
    ListKind.BUDGET_INCOME: [BudgetEntry(ek="111003", zdroj="41", analytika="000")],
    ListKind.DOCUMENT_SERIES: [
        SeriesEntry("FDŠJ", "7", "FDŠJ/XXX/RR", "Faktúry", "Školská jedáleň")
    ],
    ListKind.TRANSFERS: [TransferEntry("312001 111 000", "Voľby", "111", mock=True)],
    ListKind.COST_CENTRES: [CostCentreEntry("01", "OcÚ")],
    ListKind.EK: [EkEntry("632", "Energie"), EkEntry("632005", "Telekomunikačné služby")],
    ListKind.COFOG: [CofogEntry("09.6.0.1", "Školské stravovanie")],
    ListKind.FUNDING_SOURCES: [FundingSourceEntry("72f", "Stravné", active=False)],
    ListKind.FRAMEWORK_ACCOUNTS: [FrameworkAccountEntry("518", "Ostatné služby")],
}


@pytest.fixture(params=["sql", "memory"])
def uow(request, migrated):
    clock = FixedClock(T0)
    ids = UuidV7Generator(clock)
    if request.param == "memory":
        fake = InMemoryCodelistsUnitOfWork(clock=clock)
        return lambda: fake
    for customer_id, ico in (("c1", "00305863"), ("c2", "99900017")):
        with SqlTenancyUnitOfWork(migrated, clock=clock, ids=ids) as tenancy:
            tenancy.customers.add(Customer.create(customer_id, "Obec", Ico(ico), T0))
            tenancy.commit()
    return lambda: SqlCodelistsUnitOfWork(migrated, clock=clock, ids=ids)


def _version(kind, version_id="v1", customer_id="c1", **kwargs):
    owner = None if kind.is_global else customer_id
    return CodeListVersion.first(
        version_id,
        kind,
        owner,
        2026,
        ENTRIES[kind],
        origin=VersionOrigin.SEED,
        at=T0,
        actor="u1",
        **kwargs,
    )


@pytest.mark.parametrize("kind", list(ListKind))
def test_a_version_of_each_kind_round_trips(uow, kind):
    version = _version(
        kind,
        period="2026-08",
        source=SourceRef("Vykaz_vydaj.xlsx", "ab" * 32, 458),
        warnings=[ListWarning("duplicate_key", "Vykaz_vydaj.xlsx", (276, 277), "merged")],
        import_run_id="run1",
        note="from bundle",
    )
    with uow() as work:
        work.codelists.add(version)
        work.commit()
    with uow() as work:
        loaded = work.codelists.get(version.customer_id, "v1")
    assert loaded.entries == version.entries
    for name in (
        "kind",
        "customer_id",
        "year",
        "number",
        "status",
        "origin",
        "created_at",
        "created_by",
        "period",
        "source",
        "warnings",
        "import_run_id",
        "note",
    ):
        assert getattr(loaded, name) == getattr(version, name), name


def test_a_version_is_found_only_under_its_owner(uow):
    with uow() as work:
        work.codelists.add(_version(ListKind.ACCOUNTS))
        work.codelists.add(_version(ListKind.EK, "g1"))
        work.commit()
    with uow() as work:
        with pytest.raises(NotFound):
            work.codelists.get("c2", "v1")
        with pytest.raises(NotFound):
            work.codelists.get(None, "v1")
        with pytest.raises(NotFound):
            work.codelists.get("c1", "g1")
        assert work.codelists.get(None, "g1").kind is ListKind.EK
        assert work.codelists.active("c2", ListKind.ACCOUNTS, 2026) is None
        assert work.codelists.active_ids("c1", 2026) == {ListKind.ACCOUNTS: "v1"}
        assert work.codelists.active_ids(None, 2026) == {ListKind.EK: "g1"}
        assert work.codelists.years("c1") == [2026]
        assert work.codelists.years("c2") == []


def test_a_successor_becomes_the_active_version_and_the_history_keeps_both(uow):
    with uow() as work:
        work.codelists.add(_version(ListKind.ACCOUNTS))
        work.commit()
    with uow() as work:
        first = work.codelists.active("c1", ListKind.ACCOUNTS, 2026)
        second = first.succeed(
            "v2", first.with_deactivated("518 003"), origin=VersionOrigin.EDIT, at=T0, actor="u2"
        )
        work.codelists.save(first)
        work.codelists.add(second)
        work.commit()
    with uow() as work:
        active = work.codelists.active("c1", ListKind.ACCOUNTS, 2026)
        history = work.codelists.history("c1", ListKind.ACCOUNTS, 2026)
        old = work.codelists.get("c1", "v1")
    assert active.id == "v2" and active.number == 2
    assert [(h.id, h.number, h.status, h.entry_count) for h in history] == [
        ("v2", 2, VersionStatus.ACTIVE, 2),
        ("v1", 1, VersionStatus.SUPERSEDED, 2),
    ]
    assert old.entry("518 003").active and not active.entry("518 003").active


def test_a_rolled_back_version_is_not_stored(uow):
    with uow() as work:
        work.codelists.add(_version(ListKind.ACCOUNTS))
    with uow() as work:
        assert work.codelists.active("c1", ListKind.ACCOUNTS, 2026) is None


def test_saving_an_unknown_version_is_refused(uow):
    with uow() as work, pytest.raises(NotFound):
        work.codelists.save(_version(ListKind.ACCOUNTS))


def test_purging_a_customer_deletes_its_versions_and_entries(migrated):
    clock = FixedClock(T0)
    ids = UuidV7Generator(clock)
    with SqlTenancyUnitOfWork(migrated, clock=clock, ids=ids) as tenancy:
        tenancy.customers.add(Customer.create("c1", "Obec", Ico("00305863"), T0))
        tenancy.commit()
    with SqlCodelistsUnitOfWork(migrated, clock=clock, ids=ids) as work:
        work.codelists.add(_version(ListKind.ACCOUNTS))
        work.codelists.add(_version(ListKind.EK, "g1"))
        work.commit()
    with SqlTenancyUnitOfWork(migrated, clock=clock, ids=ids) as tenancy:
        tenancy.customers.remove("c1")
        tenancy.commit()
    with migrated.session() as session:
        assert session.scalar(select(func.count()).select_from(AccountRow)) == 0
        assert session.scalars(select(CodeListVersionRow.id)).all() == ["g1"]
