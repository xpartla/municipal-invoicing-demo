import pytest

from riso import paths
from riso.contracts import ReferenceBundle
from riso.ingest import EXPORT_FILES
from riso.reference import LocalReferenceSource, ReferenceIndex

BOLDOG = "00305863"


@pytest.fixture(scope="session")
def source() -> LocalReferenceSource:
    return LocalReferenceSource()


@pytest.fixture(scope="session")
def bundle(source: LocalReferenceSource) -> ReferenceBundle:
    return source.bundle(BOLDOG)


@pytest.fixture(scope="session")
def index(bundle: ReferenceBundle) -> ReferenceIndex:
    return ReferenceIndex(bundle)


@pytest.fixture(scope="session")
def raw_dir():
    """The exports from the accounting software. They live outside the repository, so tests
    that need them are skipped on a fresh clone."""
    raw = paths.raw_dir()
    if not all((raw / name).is_file() for name in EXPORT_FILES):
        pytest.skip(f"the raw exports are not in {raw}")
    return raw


SEED_PASSWORD = "Ukážkové-heslo-2026"


@pytest.fixture(scope="session")
def seed_template(tmp_path_factory):
    """A var directory `riso seed` filled once per run (the seed codes 74 invoices, so the
    tests that need a seeded database copy this one instead of seeding again)."""
    from riso.api.seed import seed
    from riso.identity.infrastructure.hashing import Argon2Hasher
    from riso.platform import Settings

    settings = Settings(var_dir=tmp_path_factory.mktemp("seeded") / "var", env="test")
    done = seed(settings, password=SEED_PASSWORD, hasher=Argon2Hasher.fast())
    return settings.var_dir, done


def copy_seeded(template, var_dir):
    """The seeded database (and its files) copied to `var_dir`; returns the seed's result."""
    import copy
    import shutil

    source, done = template
    shutil.copytree(source, var_dir)
    return copy.deepcopy(done)


@pytest.fixture
def seeded_copy(seed_template):
    """`seeded_copy(settings.var_dir)` stands for `seed(settings, password=SEED_PASSWORD)`."""
    return lambda var_dir: copy_seeded(seed_template, var_dir)
