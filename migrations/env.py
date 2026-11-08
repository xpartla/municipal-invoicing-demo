"""Alembic environment: every context's ORM models on the shared `metadata`, batch mode for
SQLite's ALTER, and the URL from the settings unless the caller's Config sets one."""

from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import text

from riso.platform.db import UtcDateTime, create_db_engine, metadata
from riso.platform.models import import_models
from riso.platform.settings import Settings

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

import_models()
target_metadata = metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or Settings().db_url


def _render_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    """Writes our column types as the plain SQLAlchemy types they store, so migrations do
    not import application code."""
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime()"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Foreign keys are off while migrating: SQLite's batch mode copies and drops tables,
    # which would otherwise fire ON DELETE actions. They are checked once at the end.
    engine = create_db_engine(_url(), foreign_keys=False)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                render_item=_render_item,
                compare_type=True,
                # SQLAlchemy emits BEGIN itself (riso.platform.db), so SQLite DDL runs in the
                # transaction and a failed upgrade leaves nothing half done.
                transactional_ddl=True,
            )
            with context.begin_transaction():
                context.run_migrations()
                if connection.dialect.name == "sqlite":
                    broken = connection.execute(text("PRAGMA foreign_key_check")).fetchall()
                    if broken:
                        raise RuntimeError(f"foreign key violations after migrating: {broken}")
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
