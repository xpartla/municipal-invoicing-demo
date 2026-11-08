"""`CodeListVersion`: succession, its invariants and the row edits."""

from datetime import UTC, datetime

import pytest

from riso.codelists.domain import (
    AccountEntry,
    CodeListVersion,
    CodeListVersionCreated,
    EkEntry,
    ListKind,
    VersionOrigin,
    VersionStatus,
)
from riso.shared import Conflict, InvalidState, NotFound, ValidationFailed

AT = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
ACCOUNTS = (AccountEntry("518", "000", "cost"), AccountEntry("518", "003", "cost"))


def _first(entries=ACCOUNTS, **kwargs) -> CodeListVersion:
    return CodeListVersion.first(
        "v1",
        ListKind.ACCOUNTS,
        "c1",
        2026,
        entries,
        origin=VersionOrigin.SEED,
        at=AT,
        actor=None,
        period="2026-08",
        **kwargs,
    )


def test_the_first_version_is_number_one_and_active():
    version = _first()
    assert (version.number, version.status, version.active) == (1, VersionStatus.ACTIVE, True)
    assert version.events == [
        CodeListVersionCreated("v1", ListKind.ACCOUNTS, "c1", 2026, 1, VersionOrigin.SEED, None)
    ]


def test_a_successor_supersedes_its_predecessor():
    first = _first()
    second = first.succeed(
        "v2", first.with_deactivated("518 003"), origin=VersionOrigin.EDIT, at=LATER, actor="u1"
    )
    assert (second.number, second.year, second.customer_id, second.kind) == (
        2,
        2026,
        "c1",
        ListKind.ACCOUNTS,
    )
    assert second.active and first.status is VersionStatus.SUPERSEDED
    assert second.created_by == "u1" and second.origin is VersionOrigin.EDIT
    assert second.events[-1].superseded_id == "v1"
    assert first.entry("518 003").active  # the old version is unchanged
    assert not second.entry("518 003").active


def test_a_superseded_version_has_no_successor():
    first = _first()
    first.succeed("v2", ACCOUNTS, origin=VersionOrigin.EDIT, at=LATER, actor="u1")
    with pytest.raises(InvalidState):
        first.succeed("v3", ACCOUNTS, origin=VersionOrigin.EDIT, at=LATER, actor="u1")


def test_a_global_list_has_no_customer_and_a_customer_list_needs_one():
    with pytest.raises(InvalidState):
        CodeListVersion.first(
            "g1", ListKind.EK, "c1", 2026, (), origin=VersionOrigin.SEED, at=AT, actor=None
        )
    with pytest.raises(InvalidState):
        CodeListVersion.first(
            "v1", ListKind.ACCOUNTS, None, 2026, (), origin=VersionOrigin.SEED, at=AT, actor=None
        )
    ek = CodeListVersion.first(
        "g1",
        ListKind.EK,
        None,
        2026,
        (EkEntry("632", "x"),),
        origin=VersionOrigin.SEED,
        at=AT,
        actor=None,
    )
    assert ek.customer_id is None


def test_entries_must_be_of_the_lists_kind():
    with pytest.raises(InvalidState):
        _first((EkEntry("632", "x"),))


def test_keys_are_unique_within_a_version():
    with pytest.raises(Conflict):
        _first((*ACCOUNTS, AccountEntry("518", "003", "cost", description="again")))


@pytest.mark.parametrize("year", [1999, 2101])
def test_the_year_is_plausible(year):
    with pytest.raises(ValidationFailed):
        CodeListVersion.first(
            "v1", ListKind.ACCOUNTS, "c1", year, (), origin=VersionOrigin.SEED, at=AT, actor=None
        )


def test_the_period_is_a_month():
    with pytest.raises(ValidationFailed):
        CodeListVersion.first(
            "v1",
            ListKind.ACCOUNTS,
            "c1",
            2026,
            (),
            origin=VersionOrigin.SEED,
            at=AT,
            actor=None,
            period="2026-13",
        )


def test_adding_a_row_with_a_used_key_is_refused():
    version = _first()
    added = version.with_added(AccountEntry("518", "010", "cost"))
    assert [e.key for e in added] == ["518 000", "518 003", "518 010"]
    with pytest.raises(Conflict):
        version.with_added(AccountEntry("518", "003", "cost"))


def test_editing_a_row_may_change_its_key_to_a_free_one():
    version = _first()
    edited = version.with_replaced("518 003", AccountEntry("518", "004", "cost", description="x"))
    assert [e.key for e in edited] == ["518 000", "518 004"]
    with pytest.raises(Conflict):
        version.with_replaced("518 003", AccountEntry("518", "000", "cost"))
    with pytest.raises(NotFound):
        version.with_replaced("518 999", AccountEntry("518", "999", "cost"))


def test_deactivating_keeps_the_row_and_hides_it_from_the_active_entries():
    version = _first()
    entries = version.with_deactivated("518 003")
    assert len(entries) == 2
    second = version.succeed("v2", entries, origin=VersionOrigin.EDIT, at=LATER, actor="u1")
    assert [e.key for e in second.active_entries()] == ["518 000"]
    with pytest.raises(InvalidState):
        second.with_deactivated("518 003")
    third = second.succeed(
        "v3", second.with_reactivated("518 003"), origin=VersionOrigin.EDIT, at=LATER, actor="u1"
    )
    assert [e.key for e in third.active_entries()] == ["518 000", "518 003"]
    with pytest.raises(InvalidState):
        third.with_reactivated("518 003")


def test_the_info_summarises_the_version():
    info = _first(note="from the export").info()
    assert (info.id, info.number, info.entry_count, info.period, info.note) == (
        "v1",
        1,
        2,
        "2026-08",
        "from the export",
    )
