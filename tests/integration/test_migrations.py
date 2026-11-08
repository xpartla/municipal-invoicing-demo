"""The migrations go up and down on an empty database, and the models match them."""

import importlib

from riso.platform.migrations import check, current_revision, downgrade, head_revision, upgrade
from riso.platform.models import MODEL_MODULES


def test_migrations_upgrade_check_and_downgrade(db_url):
    assert current_revision(db_url) is None
    upgrade(db_url)
    assert current_revision(db_url) == head_revision()
    check(db_url)  # raises when the models and the database differ
    downgrade(db_url, "base")
    assert current_revision(db_url) is None
    upgrade(db_url)
    assert current_revision(db_url) == head_revision()


def test_upgrading_twice_changes_nothing(db_url):
    upgrade(db_url)
    upgrade(db_url)
    assert current_revision(db_url) == head_revision()


def test_every_model_module_imports():
    for name in MODEL_MODULES:
        importlib.import_module(name)
