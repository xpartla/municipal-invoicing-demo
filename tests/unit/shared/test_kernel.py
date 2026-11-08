"""The clock, the request context, the errors and the event dispatcher."""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from riso.shared import (
    AllowAll,
    DomainEvent,
    EventDispatcher,
    FixedClock,
    PermissionDenied,
    RequestContext,
    SystemClock,
    ValidationFailed,
    local_date,
)

# --- clock -------------------------------------------------------------------------------


def test_the_system_clock_is_aware_utc():
    assert SystemClock().now().tzinfo == UTC


def test_a_fixed_clock_moves_only_when_told():
    clock = FixedClock(datetime(2026, 6, 11, 8, 0, tzinfo=UTC))
    assert clock.now() == clock.now()
    clock.advance(timedelta(hours=1))
    assert clock.now() == datetime(2026, 6, 11, 9, 0, tzinfo=UTC)
    clock.set(datetime(2026, 6, 11, 12, 0, tzinfo=timezone(timedelta(hours=2))))
    assert clock.now() == datetime(2026, 6, 11, 10, 0, tzinfo=UTC)
    assert clock.now().tzinfo == UTC


def test_a_fixed_clock_refuses_naive_times():
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 6, 11, 8, 0))


@pytest.mark.parametrize(
    ("instant", "day"),
    [
        (datetime(2026, 6, 10, 21, 59, tzinfo=UTC), date(2026, 6, 10)),  # 23:59 CEST
        (datetime(2026, 6, 10, 22, 0, tzinfo=UTC), date(2026, 6, 11)),  # midnight CEST
        (datetime(2026, 1, 10, 22, 59, tzinfo=UTC), date(2026, 1, 10)),  # 23:59 CET
        (datetime(2026, 1, 10, 23, 0, tzinfo=UTC), date(2026, 1, 11)),  # midnight CET
    ],
)
def test_days_are_counted_in_bratislava(instant, day):
    assert local_date(instant) == day


# --- request context ---------------------------------------------------------------------


class OnlyInvoicesOfC1:
    def allows(self, permission: str, customer_id: str | None, provider_id: str | None) -> bool:
        return permission == "invoice.read" and customer_id == "c1"


def test_require_raises_without_the_permission():
    ctx = RequestContext(request_id="r1", actor_id="u1", policy=OnlyInvoicesOfC1())
    ctx.require("invoice.read", "c1")
    assert ctx.allows("invoice.read", "c1")
    with pytest.raises(PermissionDenied):
        ctx.require("invoice.read", "c2")
    with pytest.raises(PermissionDenied):
        ctx.require("invoice.book", "c1")


class CreateInP1:
    def allows(self, permission: str, customer_id: str | None, provider_id: str | None) -> bool:
        return permission == "customers.create" and provider_id == "p1" and customer_id is None


def test_require_passes_the_provider_scope():
    ctx = RequestContext(request_id="r1", actor_id="u1", policy=CreateInP1())
    ctx.require("customers.create", provider_id="p1")
    with pytest.raises(PermissionDenied, match="in provider p2"):
        ctx.require("customers.create", provider_id="p2")
    with pytest.raises(PermissionDenied, match="customers.create denied$"):
        ctx.require("customers.create")


def test_an_anonymous_context_is_denied_everything():
    ctx = RequestContext.anonymous("r1")
    assert ctx.actor_id is None
    with pytest.raises(PermissionDenied):
        ctx.require("invoice.read")


def test_the_system_context_is_allowed_everything():
    ctx = RequestContext.system("r1")
    ctx.require("anything", "c1")
    assert isinstance(ctx.policy, AllowAll)


def test_an_impersonating_context_knows_its_real_actor():
    ctx = RequestContext(request_id="r1", actor_id="user", real_actor_id="admin")
    assert ctx.impersonating
    assert not RequestContext(request_id="r1", actor_id="user").impersonating


# --- errors ------------------------------------------------------------------------------


def test_a_validation_failure_names_its_field():
    error = ValidationFailed.on("address.city", "required", "required")
    assert error.message == "required"
    assert [(e.field, e.code) for e in error.errors] == [("address.city", "required")]


# --- events ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Booked(DomainEvent):
    invoice_id: str


@dataclass(frozen=True, slots=True)
class Paid(DomainEvent):
    invoice_id: str


def test_handlers_run_in_subscription_order_for_their_event_type():
    seen: list[str] = []
    dispatcher = EventDispatcher()
    dispatcher.subscribe(Booked, lambda e: seen.append(f"first {e.invoice_id}"))
    dispatcher.subscribe(Booked, lambda e: seen.append(f"second {e.invoice_id}"))
    dispatcher.subscribe(Paid, lambda e: seen.append(f"paid {e.invoice_id}"))
    dispatcher.dispatch([Booked("i1"), Paid("i2")])
    assert seen == ["first i1", "second i1", "paid i2"]


def test_a_handler_of_the_base_class_sees_every_event():
    seen: list[DomainEvent] = []
    dispatcher = EventDispatcher()
    dispatcher.subscribe(DomainEvent, seen.append)
    dispatcher.dispatch([Booked("i1"), Paid("i2")])
    assert seen == [Booked("i1"), Paid("i2")]


def test_a_failing_handler_is_logged_and_the_others_still_run(caplog):
    seen: list[str] = []

    def broken(event: Booked) -> None:
        raise RuntimeError("boom")

    dispatcher = EventDispatcher()
    dispatcher.subscribe(Booked, broken)
    dispatcher.subscribe(Booked, lambda e: seen.append(e.invoice_id))
    with caplog.at_level(logging.ERROR, logger="riso.shared.events"):
        dispatcher.dispatch([Booked("i1")])
    assert seen == ["i1"]
    assert "broken failed for Booked" in caplog.text


# --- the in-memory unit of work used by application tests --------------------------------


@dataclass(slots=True)
class Thing:
    events: list[DomainEvent]


def test_the_in_memory_unit_of_work_dispatches_on_commit_only():
    from tests.fakes.uow import InMemoryUnitOfWork

    uow = InMemoryUnitOfWork()
    with uow:
        uow.track(Thing([Booked("i1")]))
        uow.commit()
    with pytest.raises(RuntimeError), uow:
        uow.track(Thing([Booked("i2")]))
        raise RuntimeError("use case failed")
    assert uow.dispatched == [Booked("i1")]
    assert (uow.commits, uow.rollbacks) == (1, 1)
