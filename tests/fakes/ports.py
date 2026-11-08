"""Fakes of the technical ports: file storage, mail and the job queue."""

import hashlib
import io
from datetime import datetime
from typing import Any, BinaryIO

from riso.shared import NotFound, ValidationFailed
from riso.shared.ports import MailMessage, StoredFile


class InMemoryFileStorage:
    """Content-addressed like `LocalFileStorage`, kept in a dict. The month is fixed."""

    def __init__(self, month: str = "2026/06") -> None:
        self.month = month
        self.files: dict[str, bytes] = {}

    def put(self, data: bytes | BinaryIO, *, owner: str, extension: str) -> StoredFile:
        if not owner or "/" in owner or ".." in owner:
            raise ValidationFailed.on("owner", "not a valid storage owner")
        content = data if isinstance(data, bytes) else data.read()
        sha = hashlib.sha256(content).hexdigest()
        key = f"{owner}/{self.month}/{sha}.{extension.lower().lstrip('.')}"
        created = key not in self.files
        self.files[key] = content
        return StoredFile(key, sha, len(content), created)

    def open(self, key: str) -> BinaryIO:
        if key not in self.files:
            raise NotFound(f"no stored file {key!r}")
        return io.BytesIO(self.files[key])

    def exists(self, key: str) -> bool:
        return key in self.files

    def delete(self, key: str) -> None:
        self.files.pop(key, None)


class RecordingMailSender:
    def __init__(self) -> None:
        self.sent: list[MailMessage] = []

    def send(self, message: MailMessage) -> str:
        self.sent.append(message)
        return f"mail-{len(self.sent)}"


class RecordingJobQueue:
    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []

    def enqueue(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        customer_id: str | None = None,
        created_by: str | None = None,
        run_after: datetime | None = None,
    ) -> str:
        job_id = f"job-{len(self.jobs) + 1}"
        self.jobs.append(
            {
                "id": job_id,
                "kind": kind,
                "payload": payload,
                "customer_id": customer_id,
                "created_by": created_by,
                "run_after": run_after,
            }
        )
        return job_id


class RecordingAudit:
    """An `AuditRecorder` keeping its entries in a list. Like the real one, entries recorded in
    a unit of work that rolls back are dropped (the fakes' stores call `begin`/`rollback`)."""

    def __init__(self) -> None:
        self.entries: list[dict] = []
        self._mark = 0

    def record(
        self, ctx, action, *, target_type=None, target_id=None, customer_id=None, details=None
    ):
        self.entries.append(
            {
                "action": action,
                "actor_id": ctx.actor_id,
                "real_actor_id": ctx.real_actor_id,
                "customer_id": customer_id or ctx.customer_id,
                "target_type": target_type,
                "target_id": target_id,
                "details": dict(details or {}),
            }
        )

    def begin(self) -> None:
        self._mark = len(self.entries)

    def commit(self) -> None:
        self._mark = len(self.entries)

    def rollback(self) -> None:
        del self.entries[self._mark :]

    def actions(self) -> list[str]:
        return [e["action"] for e in self.entries]
