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
