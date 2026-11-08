"""The database: engine, SQLite pragmas, the shared `metadata`, and sessions (plan §4.5).

SQLite runs in WAL mode with foreign keys on and a busy timeout. SQLAlchemy, not the
sqlite3 module, emits `BEGIN`, so a transaction can start as `BEGIN IMMEDIATE` and take the
write lock up front; number allocation and job claiming need that. Nothing here is
SQLite-only in the SQL itself, so PostgreSQL stays a change of URL.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Dialect, Engine, MetaData, TypeDecorator, create_engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """The declarative base of every context's ORM models; they share one `metadata`."""

    metadata = metadata


class UtcDateTime(TypeDecorator[datetime]):
    """A timezone-aware UTC instant. SQLite keeps no time zone, so the value is stored as
    naive UTC and read back as aware UTC; a naive value is refused on the way in."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("instants must be timezone-aware")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


BUSY_TIMEOUT_MS = 5000
_IMMEDIATE = "riso_begin_immediate"


def create_db_engine(
    url: str, *, busy_timeout_ms: int = BUSY_TIMEOUT_MS, foreign_keys: bool = True
) -> Engine:
    """An engine for `url`. For SQLite: WAL, foreign keys (unless turned off, as migrations
    do), the busy timeout, and `BEGIN` emitted by SQLAlchemy. A file database's directory is
    created when missing."""
    parsed = make_url(url)
    connect_args: dict[str, Any] = {}
    if parsed.get_backend_name() == "sqlite":
        # The worker thread and the request threads share the pool, never a connection.
        connect_args["check_same_thread"] = False
        if parsed.database and parsed.database != ":memory:":
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args=connect_args)
    if engine.dialect.name == "sqlite":
        _configure_sqlite(engine, busy_timeout_ms, foreign_keys)
    return engine


def _configure_sqlite(engine: Engine, busy_timeout_ms: int, foreign_keys: bool) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        # Stop the sqlite3 module from emitting BEGIN itself; _on_begin does it instead.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute(f"PRAGMA foreign_keys={'ON' if foreign_keys else 'OFF'}")
            cursor.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        finally:
            cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(connection: Connection) -> None:
        immediate = connection.get_execution_options().get(_IMMEDIATE, False)
        connection.exec_driver_sql("BEGIN IMMEDIATE" if immediate else "BEGIN")


class Database:
    """The engine and the session factories of one database."""

    def __init__(self, url: str, *, busy_timeout_ms: int = BUSY_TIMEOUT_MS) -> None:
        self.url = url
        self.engine = create_db_engine(url, busy_timeout_ms=busy_timeout_ms)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)
        # Same pool and event hooks; its transactions begin with BEGIN IMMEDIATE on SQLite.
        self._immediate_sessions = sessionmaker(
            self.engine.execution_options(**{_IMMEDIATE: True}), expire_on_commit=False
        )

    def session(self, *, immediate: bool = False) -> Session:
        """A new session. With `immediate`, its transaction takes the write lock when it
        begins, so concurrent writers wait (up to the busy timeout) instead of failing
        later."""
        return (self._immediate_sessions if immediate else self._sessions)()

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        with self.engine.connect() as connection:
            yield connection

    def dispose(self) -> None:
        self.engine.dispose()
