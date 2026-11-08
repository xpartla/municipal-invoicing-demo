"""The modules that define ORM models. Alembic and the test fixtures import them all, so the
shared `metadata` knows every table. Add a context's `infrastructure.orm` here when it gets
tables."""

import importlib

MODEL_MODULES: tuple[str, ...] = (
    "riso.platform.mail",
    "riso.jobs.infrastructure.orm",
    "riso.identity.infrastructure.orm",
    "riso.tenancy.infrastructure.orm",
    "riso.audit.infrastructure.orm",
)


def import_models() -> None:
    for name in MODEL_MODULES:
        importlib.import_module(name)
