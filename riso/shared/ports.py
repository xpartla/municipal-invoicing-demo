"""Ports for technical services that use cases in every context need: file storage, mail
and the audit log. The adapters live in `riso.platform`; tests use fakes from `tests/fakes`."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import BinaryIO, Protocol

from riso.shared.context import RequestContext


@dataclass(frozen=True, slots=True)
class StoredFile:
    key: str
    """Where the file is, relative to the store: `<owner>/<yyyy>/<mm>/<sha256>.<ext>`."""
    sha256: str
    size: int
    created: bool
    """False when the same content was already stored under this key."""


class FileStorage(Protocol):
    """Content-addressed file storage (plan §4.5). The same content for the same owner and
    month lands on the same key, so storing it twice keeps one copy."""

    def put(self, data: bytes | BinaryIO, *, owner: str, extension: str) -> StoredFile: ...

    def open(self, key: str) -> BinaryIO:
        """Opens a stored file for reading; raises `NotFound` when it is absent."""
        ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None:
        """Removes a stored file; does nothing when it is already gone."""
        ...


@dataclass(frozen=True, slots=True)
class MailMessage:
    to: str
    subject: str
    body: str
    template: str
    """The template it was rendered from, for the outbox viewer."""
    customer_id: str | None = None
    user_id: str | None = None


class MailSender(Protocol):
    """Sends mail. In phase 2 every message goes to the outbox in the current transaction,
    so a mail is recorded exactly when the change that caused it commits."""

    def send(self, message: MailMessage) -> str:
        """Returns the outbox ID of the message."""
        ...


class Mailer(Protocol):
    """Renders a mail template and sends it (to the outbox) in the current transaction."""

    def send(
        self,
        template: str,
        to: str,
        *,
        user_id: str | None = None,
        customer_id: str | None = None,
        **values: str,
    ) -> str:
        """Returns the outbox ID of the message."""
        ...


class AuditRecorder(Protocol):
    """Appends to the audit log in the current transaction (plan §4.7, §12). Every write use
    case records what it did; the entry carries the actor, the real actor when an admin
    impersonates, the acting customer, the request ID and the client's address from `ctx`.

    `details` holds IDs and field names, never invoice content, names or IBANs."""

    def record(
        self,
        ctx: RequestContext,
        action: str,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
        customer_id: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        """`customer_id` defaults to the context's acting customer."""
        ...
