"""The committed global lists, `data/global/<year>/*.csv`, as version 1 of each global list of
the year (`riso seed`). P2-M3 replaces this with import templates.

Each file has the header `code,name`; see `data/global/2026/README.md` for the sources.
"""

import csv
import hashlib
import io
from datetime import datetime
from pathlib import Path

from riso.codelists.domain import (
    GLOBAL_KINDS,
    CodeListVersion,
    Entry,
    ListKind,
    SourceRef,
    VersionOrigin,
    parse_entry,
)
from riso.shared.errors import ValidationFailed
from riso.shared.ids import IdGenerator

FILES: dict[ListKind, str] = {
    ListKind.EK: "ek.csv",
    ListKind.COFOG: "cofog.csv",
    ListKind.FUNDING_SOURCES: "funding_sources.csv",
    ListKind.FRAMEWORK_ACCOUNTS: "framework_accounts.csv",
}
assert tuple(FILES) == GLOBAL_KINDS


class GlobalListError(ValueError):
    """A committed global list does not read; the message names the file and the row."""


def global_years(root: Path) -> list[int]:
    if not root.is_dir():
        return []
    return sorted(int(d.name) for d in root.iterdir() if d.is_dir() and d.name.isdigit())


def read_entries(path: Path, kind: ListKind) -> tuple[list[Entry], SourceRef]:
    data = path.read_bytes()
    reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
    if reader.fieldnames != ["code", "name"]:
        raise GlobalListError(f"{path.name}: the header is not 'code,name'")
    entries = []
    for number, row in enumerate(reader, start=2):
        try:
            entries.append(parse_entry(kind, {"code": row["code"], "name": row["name"]}))
        except ValidationFailed as exc:
            raise GlobalListError(f"{path.name} row {number}: {exc.message}") from exc
    return entries, SourceRef(path.name, hashlib.sha256(data).hexdigest(), len(entries))


def global_versions(root: Path, year: int, ids: IdGenerator, at: datetime) -> list[CodeListVersion]:
    """Version 1 of each global list the year's folder has a file for."""
    versions = []
    for kind, name in FILES.items():
        path = root / str(year) / name
        if not path.is_file():
            continue
        entries, source = read_entries(path, kind)
        versions.append(
            CodeListVersion.first(
                ids.new(),
                kind,
                None,
                year,
                entries,
                origin=VersionOrigin.SEED,
                at=at,
                actor=None,
                source=source,
                note=f"from data/global/{year}/{name}",
            )
        )
    return versions
