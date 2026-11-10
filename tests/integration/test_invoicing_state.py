"""Supplier memory and number series on the database (P2-M4-T02): after `riso seed` the
engine reads the same objects as the demo's files; the repositories keep what they are
given; and two bookings at once never take the same number."""

import threading
from datetime import UTC, date, datetime, timedelta

import pytest

from riso import paths
from riso.api.composition import build_services
from riso.audit.domain.event import AuditFilter
from riso.contracts import Counters, Precedent, SupplierMemory
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.invoicing.application import list_series, set_last_used, take_number
from riso.invoicing.domain.numbering import HolderKind, Newcomer, NumberFrozen
from riso.platform import Settings
from riso.shared import AllowAll, InvalidState, NotFound, RequestContext, ValidationFailed

BOLDOG = "00305863"
INITIAL = paths.INITIAL_STATE_DIR / BOLDOG
CTX = RequestContext("test", None, policy=AllowAll())
T0 = datetime(2026, 7, 1, 8, tzinfo=UTC)


@pytest.fixture
def env(tmp_path, seeded_copy):
    settings = Settings(var_dir=tmp_path / "var", env="test")
    done = seeded_copy(settings.var_dir)
    services = build_services(settings, hasher=Argon2Hasher.fast())
    yield services, done.customers["Obec Boldog"]
    services.close()


def _newcomer(invoice_id: str, day: int, sequence: int | None = None) -> Newcomer:
    return Newcomer(invoice_id, date(2026, 6, day), T0 + timedelta(minutes=day), sequence)


def test_the_seeded_state_equals_the_demo_files(env):
    services, boldog = env
    state = services.supplier_state()
    memory = SupplierMemory.model_validate_json((INITIAL / "supplier_memory.json").read_bytes())
    counters = Counters.model_validate_json((INITIAL / "counters.json").read_bytes())
    assert state.memory(boldog) == memory
    assert state.counters(boldog) == counters
    assert memory.suppliers and counters.used_numbers  # a meaningful comparison


def test_the_seeded_series_hold_the_initial_numbers(env):
    services, boldog = env
    views = {v.series: v for v in list_series(CTX, services.uow(immediate=False), boldog, 2026)}
    assert set(views) == {"FD", "FDŠJ"}
    fd = views["FD"]
    assert (fd.last_used, fd.last_used_number, fd.next_number) == (222, "FD/222/26", "FD/223/26")
    counters = Counters.model_validate_json((INITIAL / "counters.json").read_bytes())
    assert sorted(u.number for u in fd.used) == sorted(counters.used_numbers)
    assert {(u.kind, u.frozen) for u in fd.used} == {(HolderKind.EXTERNAL.value, True)}
    assert views["FDŠJ"].last_used == 0 and views["FDŠJ"].stored


def test_booking_numbers_moves_the_later_ones_and_persists(env):
    services, boldog = env
    with services.uow() as uow:
        first = take_number(uow, boldog, "FD", 2026, _newcomer("i1", 10), requested=None)
        second = take_number(uow, boldog, "FD", 2026, _newcomer("i2", 12), requested=None)
        uow.commit()
    assert (first.number, second.number) == ("FD/223/26", "FD/224/26")
    with services.uow() as uow:
        placed = take_number(uow, boldog, "FD", 2026, _newcomer("i3", 11), requested=None)
        uow.commit()
    assert placed.number == "FD/224/26"
    assert [(s.invoice_id, s.old, s.new) for s in placed.shifts] == [
        ("i2", "FD/224/26", "FD/225/26")
    ]
    with services.uow(immediate=False) as uow:
        series = uow.number_series.find(boldog, "FD", 2026)
        assert series is not None and series.last_used == 225
        by_invoice = {h.invoice_id: series.number(h.sequence) for h in series.holders}
        assert {k: v for k, v in by_invoice.items() if k} == {
            "i1": "FD/223/26",
            "i3": "FD/224/26",
            "i2": "FD/225/26",
        }
        used = uow.number_series.used_numbers(boldog)
    assert used[-3:] == ["FD/223/26", "FD/225/26", "FD/224/26"]  # the order first used


def test_unbooking_frees_the_last_and_reserves_the_others(env):
    services, boldog = env
    with services.uow() as uow:
        for invoice, day in (("i1", 10), ("i2", 12)):
            take_number(uow, boldog, "FD", 2026, _newcomer(invoice, day), requested=None)
        uow.commit()
    with services.uow() as uow:
        series = uow.number_series.find(boldog, "FD", 2026)
        assert series is not None
        series.release("i1", T0)
        series.release("i2", T0)
        uow.number_series.save(series)
        uow.commit()
    with services.uow(immediate=False) as uow:
        series = uow.number_series.find(boldog, "FD", 2026)
        assert series is not None and series.last_used == 223
        reserved = series.holder_of("i1")
        assert reserved is not None and reserved.kind is HolderKind.RESERVED
        assert series.holder_of("i2") is None
        assert [s.series for s in uow.number_series.holding(boldog, "i1")] == ["FD"]


def test_a_frozen_number_refuses_the_booking_and_changes_nothing(env):
    services, boldog = env
    with services.uow() as uow:
        take_number(uow, boldog, "FD", 2026, _newcomer("i1", 12), requested=None)
        series = uow.number_series.find(boldog, "FD", 2026)
        assert series is not None and series.freeze("i1", T0)
        uow.number_series.save(series)
        uow.commit()
    with services.uow() as uow, pytest.raises(NumberFrozen, match="FD/223/26"):
        take_number(uow, boldog, "FD", 2026, _newcomer("i2", 11), requested=None)
    with services.uow(immediate=False) as uow:
        series = uow.number_series.find(boldog, "FD", 2026)
        assert series is not None and [h.invoice_id for h in series.holders if h.invoice_id] == [
            "i1"
        ]


def test_a_series_the_list_does_not_have_is_refused(env):
    services, boldog = env
    with services.uow() as uow, pytest.raises(InvalidState, match="has no series XY"):
        take_number(uow, boldog, "XY", 2026, _newcomer("i1", 10), requested=None)


def test_editing_the_counter_is_audited_and_cannot_go_below_a_used_number(env):
    services, boldog = env
    view = set_last_used(CTX, services.uow(), boldog, "FD", 2026, 230)
    assert (view.last_used, view.next_number) == (230, "FD/231/26")
    with services.uow(immediate=False) as uow:
        events, _ = uow.audit_log.page(
            AuditFilter(customer_id=boldog, action="number_series.last_used_set")
        )
    assert events[0].details == {"series": "FD", "year": 2026, "before": 222, "after": 230}
    with pytest.raises(ValidationFailed, match="FD/222/26 is used"):
        set_last_used(CTX, services.uow(), boldog, "FD", 2026, 100)
    with pytest.raises(NotFound, match="2027 document series list has no series FDŠJ"):
        set_last_used(CTX, services.uow(), boldog, "FDŠJ", 2027, 5)  # no 2027 lists


def test_precedents_newest_first_removed_and_renumbered_with_their_invoice(env):
    services, boldog = env
    precedent = Precedent.model_validate(
        {
            "document_number": "FD/223/26",
            "booking_date": "2026-06-23",
            "amount": 93.71,
            "lines": [
                {
                    "budget_key": "632005 41 01 110 000",
                    "md": "518 003",
                    "dal": "321 000",
                    "budget_text": "telefon,fax",
                    "posting_text": "tel.",
                }
            ],
            "source": "feedback",
        }
    )
    state = services.supplier_state()
    before = state.memory(boldog)
    telekom = next(s for s in before.suppliers if s.name.startswith("Slovak Telekom"))
    with services.uow() as uow:
        uow.supplier_memory.add_precedent(
            boldog, telekom.ico, telekom.name, precedent, invoice_id="i1"
        )
        uow.supplier_memory.add_precedent(
            boldog, "35815256", "Nový dodávateľ", precedent, invoice_id="i1"
        )
        uow.commit()
    after = state.memory(boldog)
    record = after.find(telekom.ico)
    assert record is not None and record.precedents[0] == precedent
    assert record.precedents[1:] == telekom.precedents
    assert after.suppliers[-1].ico == "35815256"  # a new supplier comes last
    with services.uow() as uow:
        assert uow.supplier_memory.renumber(boldog, "i1", "FD/224/26") == 2
        uow.commit()
    record = state.memory(boldog).find(telekom.ico)
    assert record is not None and record.precedents[0].document_number == "FD/224/26"
    with services.uow() as uow:
        assert uow.supplier_memory.remove_precedents_of(boldog, "i1") == 2
        uow.commit()
    assert state.memory(boldog) == before  # the new supplier went with its only precedent


def test_two_bookings_at_once_never_take_the_same_number(env):
    services, boldog = env
    taken: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()
    start = threading.Barrier(2)

    def book(prefix: str) -> None:
        try:
            start.wait()
            for n in range(15):
                with services.uow() as uow:  # its own connection, BEGIN IMMEDIATE
                    placement = take_number(
                        uow, boldog, "FD", 2026, _newcomer(f"{prefix}{n}", 1 + n), requested=None
                    )
                    uow.commit()
                with lock:
                    taken.append(placement.number)
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=book, args=(p,)) for p in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    with services.uow(immediate=False) as uow:
        series = uow.number_series.find(boldog, "FD", 2026)
        assert series is not None
        booked = [h for h in series.holders if h.kind is HolderKind.BOOKED]
    sequences = [h.sequence for h in booked]
    assert len(booked) == 30 and len(set(sequences)) == 30
    assert sorted(sequences) == list(range(223, 253))
    assert len(taken) == 30
