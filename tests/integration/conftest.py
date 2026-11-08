"""Integration fixtures: a temporary SQLite file per test."""

from collections.abc import Iterator

import pytest

from riso.platform import Database
from riso.platform.migrations import upgrade


@pytest.fixture
def db_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def database(db_url) -> Iterator[Database]:
    """An empty database, without the migrations."""
    db = Database(db_url)
    yield db
    db.dispose()


@pytest.fixture
def migrated(db_url) -> Iterator[Database]:
    """A database upgraded to the newest migration."""
    upgrade(db_url)
    db = Database(db_url)
    yield db
    db.dispose()
