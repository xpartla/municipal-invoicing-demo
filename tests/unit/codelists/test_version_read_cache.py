"""The cache of what Domov reads from a code list version (P2-M7-T03): one read per version,
even when requests for it come at once, and the oldest versions dropped."""

import threading
import time

from riso.codelists.application.reporting import VersionReadCache


def test_a_version_is_read_once_even_by_concurrent_requests():
    cache: VersionReadCache[int] = VersionReadCache()
    loads = []

    def load() -> int:
        loads.append(1)
        time.sleep(0.05)
        return 42

    found = []
    threads = [
        threading.Thread(target=lambda: found.append(cache.read("v1", load))) for _ in range(8)
    ]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert found == [42] * 8 and len(loads) == 1
    assert cache.read("v1", lambda: 0) == 42


def test_the_oldest_versions_are_dropped():
    cache: VersionReadCache[str] = VersionReadCache(size=2)
    for version in ("a", "b"):
        cache.read(version, lambda v=version: v)
    cache.read("a", lambda: "never")  # a is the most recent now
    cache.read("c", lambda: "c")
    assert cache.read("a", lambda: "again") == "a"
    assert cache.read("b", lambda: "reloaded") == "reloaded"
    cache.clear()
    assert cache.read("a", lambda: "fresh") == "fresh"
