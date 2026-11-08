"""Local content-addressed storage: round trips, deduplication, and keys that cannot escape."""

import hashlib
import io
from datetime import UTC, datetime

import pytest

from riso.platform.storage import LocalFileStorage
from riso.shared import FixedClock, NotFound, ValidationFailed

PDF = b"%PDF-1.7 synthetic test content\n"


@pytest.fixture
def storage(tmp_path) -> LocalFileStorage:
    # 23:30 UTC on 31 May is already 1 June in Bratislava.
    return LocalFileStorage(
        tmp_path / "files", FixedClock(datetime(2026, 5, 31, 23, 30, tzinfo=UTC))
    )


def test_a_file_round_trips(storage):
    stored = storage.put(PDF, owner="c1", extension="pdf")
    sha = hashlib.sha256(PDF).hexdigest()
    assert stored.key == f"c1/2026/06/{sha}.pdf"
    assert (stored.sha256, stored.size, stored.created) == (sha, len(PDF), True)
    assert storage.exists(stored.key)
    with storage.open(stored.key) as handle:
        assert handle.read() == PDF


def test_the_same_content_is_stored_once(storage):
    first = storage.put(PDF, owner="c1", extension="pdf")
    second = storage.put(io.BytesIO(PDF), owner="c1", extension=".PDF")
    assert second.key == first.key
    assert not second.created
    folder = storage.root / "c1" / "2026" / "06"
    assert [p.name for p in folder.iterdir()] == [f"{first.sha256}.pdf"]


def test_a_large_stream_is_hashed_in_chunks(storage):
    data = bytes(range(256)) * 20_000  # about 5 MB
    stored = storage.put(io.BytesIO(data), owner="global", extension="xlsx")
    assert stored.sha256 == hashlib.sha256(data).hexdigest()
    assert stored.size == len(data)


def test_owners_are_kept_apart(storage):
    assert storage.put(PDF, owner="c1", extension="pdf").key.startswith("c1/")
    assert storage.put(PDF, owner="c2", extension="pdf").key.startswith("c2/")


def test_deleting_is_idempotent(storage):
    stored = storage.put(PDF, owner="c1", extension="pdf")
    storage.delete(stored.key)
    storage.delete(stored.key)
    assert not storage.exists(stored.key)
    with pytest.raises(NotFound):
        storage.open(stored.key)


@pytest.mark.parametrize(
    "key",
    [
        "../c1/2026/06/" + "a" * 64 + ".pdf",
        "/etc/passwd",
        "c1/2026/06/../../../outside.pdf",
        "c1/2026/06/" + "a" * 64 + ".pdf/..",
        "c1/2026/06/not-a-hash.pdf",
    ],
)
def test_keys_cannot_leave_the_store(storage, key):
    assert not storage.exists(key)
    with pytest.raises(NotFound):
        storage.open(key)


@pytest.mark.parametrize(("owner", "extension"), [("../c1", "pdf"), ("c1", "p/df"), ("", "pdf")])
def test_invalid_owners_and_extensions_are_refused(storage, owner, extension):
    with pytest.raises(ValidationFailed):
        storage.put(PDF, owner=owner, extension=extension)


def test_no_temporary_files_are_left_behind(storage):
    storage.put(PDF, owner="c1", extension="pdf")
    storage.put(PDF, owner="c1", extension="pdf")
    leftovers = [p for p in storage.root.rglob(".upload-*")]
    assert leftovers == []


# The fake used by application tests behaves like the real store where it matters.
@pytest.mark.parametrize("make", ["local", "fake"])
def test_the_fake_and_the_local_store_agree(tmp_path, make):
    from tests.fakes.ports import InMemoryFileStorage

    store = (
        LocalFileStorage(tmp_path, FixedClock(datetime(2026, 6, 11, tzinfo=UTC)))
        if make == "local"
        else InMemoryFileStorage("2026/06")
    )
    first = store.put(PDF, owner="c1", extension="pdf")
    second = store.put(io.BytesIO(PDF), owner="c1", extension="PDF")
    assert first.key == second.key == f"c1/2026/06/{hashlib.sha256(PDF).hexdigest()}.pdf"
    assert (first.created, second.created) == (True, False)
    assert store.open(first.key).read() == PDF
    store.delete(first.key)
    assert not store.exists(first.key)
    with pytest.raises(NotFound):
        store.open(first.key)
    with pytest.raises(ValidationFailed):
        store.put(PDF, owner="../x", extension="pdf")
