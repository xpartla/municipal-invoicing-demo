"""The SQLAlchemy unit of work: commit, rollback, and events only after a commit."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, insert, select
from sqlalchemy.exc import IntegrityError

from riso.platform import SqlUnitOfWork
from riso.shared import DomainEvent, EventDispatcher, FixedClock, UuidV7Generator

test_metadata = MetaData()
widgets = Table(
    "widgets",
    test_metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(20), unique=True, nullable=False),
)


@dataclass(frozen=True, slots=True)
class WidgetMade(DomainEvent):
    widget_id: int


@dataclass(slots=True)
class Widget:
    id: int
    name: str
    events: list[DomainEvent] = field(default_factory=list)

    def make(self) -> None:
        self.events.append(WidgetMade(self.id))


class WidgetUnitOfWork(SqlUnitOfWork):
    def add(self, widget: Widget) -> None:
        """What a repository does: write the row and track the aggregate."""
        self.session.execute(insert(widgets).values(id=widget.id, name=widget.name))
        self.track(widget)


@pytest.fixture
def setup(database):
    test_metadata.create_all(database.engine)
    dispatcher = EventDispatcher()
    clock = FixedClock(datetime(2026, 11, 8, tzinfo=UTC))

    def uow() -> WidgetUnitOfWork:
        return WidgetUnitOfWork(
            database, clock=clock, ids=UuidV7Generator(clock), dispatcher=dispatcher
        )

    return database, dispatcher, uow


def names(database) -> list[str]:
    with database.session() as session:
        return list(session.execute(select(widgets.c.name).order_by(widgets.c.id)).scalars())


def made_widget(widget_id: int, name: str) -> Widget:
    widget = Widget(widget_id, name)
    widget.make()
    return widget


def test_a_commit_persists(setup):
    database, _, uow = setup
    with uow() as work:
        work.add(made_widget(1, "a"))
        work.commit()
    assert names(database) == ["a"]


def test_leaving_without_a_commit_rolls_back(setup):
    database, _, uow = setup
    with uow() as work:
        work.add(made_widget(1, "a"))
    assert names(database) == []


def test_an_exception_rolls_back_and_drops_the_events(setup):
    database, dispatcher, uow = setup
    seen: list[DomainEvent] = []
    dispatcher.subscribe(WidgetMade, seen.append)
    widget = made_widget(1, "a")
    with pytest.raises(RuntimeError), uow() as work:
        work.add(widget)
        raise RuntimeError("use case failed")
    assert names(database) == []
    assert seen == []
    assert widget.events == []


def test_events_are_dispatched_after_the_commit_and_see_its_data(setup):
    database, dispatcher, uow = setup
    seen_rows: list[list[str]] = []
    # The handler reads through its own session: the row is there only after the commit.
    dispatcher.subscribe(WidgetMade, lambda event: seen_rows.append(names(database)))
    widget = made_widget(1, "a")
    with uow() as work:
        work.add(widget)
        assert seen_rows == []
        work.commit()
        assert seen_rows == [["a"]]
    assert widget.events == []


def test_a_failed_commit_dispatches_nothing(setup):
    database, dispatcher, uow = setup
    seen: list[DomainEvent] = []
    dispatcher.subscribe(WidgetMade, seen.append)
    with uow() as work:
        work.add(made_widget(1, "a"))
        work.commit()
    seen.clear()
    with pytest.raises(IntegrityError), uow() as work:
        work.add(made_widget(2, "a"))  # the name is unique
        work.commit()
    assert seen == []
    assert names(database) == ["a"]


def test_an_aggregate_tracked_twice_dispatches_its_events_once(setup):
    _, dispatcher, uow = setup
    seen: list[DomainEvent] = []
    dispatcher.subscribe(WidgetMade, seen.append)
    widget = made_widget(1, "a")
    with uow() as work:
        work.add(widget)
        work.track(widget)
        work.commit()
    assert seen == [WidgetMade(1)]


def test_the_unit_of_work_carries_the_clock_and_the_id_generator(setup):
    _, _, uow = setup
    with uow() as work:
        assert work.clock.now() == datetime(2026, 11, 8, tzinfo=UTC)
        assert work.ids.new() < work.ids.new()
