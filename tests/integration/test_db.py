"""The SQLite engine: pragmas, foreign keys, and BEGIN IMMEDIATE taking the write lock."""

import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, insert, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from riso.platform import Database

test_metadata = MetaData()
parents = Table("parents", test_metadata, Column("id", Integer, primary_key=True))
children = Table(
    "children",
    test_metadata,
    Column("id", Integer, primary_key=True),
    Column("parent_id", ForeignKey("parents.id"), nullable=False),
    Column("name", String(20)),
)


@pytest.fixture
def tables(database):
    test_metadata.create_all(database.engine)
    return database


def test_pragmas_are_set_on_every_connection(database):
    with database.connect() as connection:
        pragma = lambda name: connection.exec_driver_sql(f"PRAGMA {name}").scalar()  # noqa: E731
        assert pragma("journal_mode") == "wal"
        assert pragma("foreign_keys") == 1
        assert pragma("busy_timeout") == 5000
        assert pragma("synchronous") == 1  # NORMAL


def test_the_database_directory_is_created(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'nested' / 'dir' / 'riso.db'}")
    with db.connect() as connection:
        connection.execute(text("select 1"))
    db.dispose()
    assert (tmp_path / "nested" / "dir" / "riso.db").is_file()


def test_foreign_keys_are_enforced(tables):
    with tables.session() as session, pytest.raises(IntegrityError):
        session.execute(insert(children).values(id=1, parent_id=99))
        session.commit()


def test_an_immediate_transaction_holds_the_write_lock_from_its_start(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'lock.db'}", busy_timeout_ms=100)
    test_metadata.create_all(db.engine)
    with db.session(immediate=True) as holder:
        holder.execute(select(parents)).all()  # only a read, but BEGIN IMMEDIATE locked
        with db.session() as other, pytest.raises(OperationalError, match="locked"):
            other.execute(insert(parents).values(id=1))
            other.commit()
        holder.rollback()
    db.dispose()


def test_a_plain_transaction_that_only_reads_does_not_block_writers(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'nolock.db'}", busy_timeout_ms=100)
    test_metadata.create_all(db.engine)
    with db.session() as reader:
        reader.execute(select(parents)).all()
        with db.session() as writer:
            writer.execute(insert(parents).values(id=1))
            writer.commit()
        reader.rollback()
    with db.session() as session:
        assert session.execute(select(parents.c.id)).scalars().all() == [1]
    db.dispose()
