"""Local, content-addressed file storage: `<root>/<owner>/<yyyy>/<mm>/<sha256>.<ext>`.

The owner is a customer ID, or `global` for the platform's own files. The month is the
upload's month in Bratislava. Files are written to a temporary name and renamed into place,
so a reader never sees half a file. Phase 2.5 adds an Azure Blob adapter for the same port.
"""

import hashlib
import os
import re
import tempfile
from collections.abc import Iterable
from functools import partial
from pathlib import Path
from typing import BinaryIO

from riso.shared.clock import Clock, SystemClock, local_date
from riso.shared.errors import NotFound, ValidationFailed
from riso.shared.ports import StoredFile

_OWNER = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_EXTENSION = re.compile(r"^[a-z0-9]{1,8}$")
_KEY = re.compile(r"^[A-Za-z0-9_-]{1,64}/\d{4}/\d{2}/[0-9a-f]{64}\.[a-z0-9]{1,8}$")
_CHUNK = 1 << 20


class LocalFileStorage:
    def __init__(self, root: Path, clock: Clock | None = None) -> None:
        self.root = root
        self._clock = clock or SystemClock()

    def put(self, data: bytes | BinaryIO, *, owner: str, extension: str) -> StoredFile:
        if not _OWNER.match(owner):
            raise ValidationFailed.on("owner", "not a valid storage owner")
        extension = extension.lower().lstrip(".")
        if not _EXTENSION.match(extension):
            raise ValidationFailed.on("extension", "not a valid file extension")
        day = local_date(self._clock.now())
        folder = self.root / owner / f"{day.year:04d}" / f"{day.month:02d}"
        folder.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256()
        size = 0
        handle, temporary = tempfile.mkstemp(dir=folder, prefix=".upload-")
        try:
            with os.fdopen(handle, "wb") as out:
                for chunk in _chunks(data):
                    digest.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
            sha256 = digest.hexdigest()
            target = folder / f"{sha256}.{extension}"
            if target.exists():
                return StoredFile(self._key(target), sha256, size, created=False)
            os.replace(temporary, target)
            return StoredFile(self._key(target), sha256, size, created=True)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def open(self, key: str) -> BinaryIO:
        path = self._path(key)
        try:
            return path.open("rb")
        except FileNotFoundError as exc:
            raise NotFound(f"no stored file {key}") from exc

    def exists(self, key: str) -> bool:
        return bool(_KEY.match(key)) and self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def _key(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _path(self, key: str) -> Path:
        # The pattern rules out absolute paths and "..", so a key never leaves the root.
        if not _KEY.match(key):
            raise NotFound(f"no stored file {key!r}")
        return self.root / key


def _chunks(data: bytes | BinaryIO) -> Iterable[bytes]:
    if isinstance(data, bytes | bytearray):
        return [bytes(data)]
    return iter(partial(data.read, _CHUNK), b"")
