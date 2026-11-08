"""Mail: the outbox table, the sender that writes to it, and the template renderer.

Every mail goes to `mail_outbox` in the transaction of the change that caused it (plan
§5.3); the admin's outbox viewer reads it. Sending through SMTP is optional configuration
and arrives with phase 2.5, so `sent_at` stays empty for now.

Templates are plain UTF-8 text files named `<name>.<locale>.txt`: the first line is
`Subject: …`, then a blank line, then the body. `$name` placeholders are filled with
`string.Template`, so a template cannot run code, and a missing value is an error.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from string import Template

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from riso.platform.db import Base, UtcDateTime
from riso.shared.clock import Clock
from riso.shared.errors import NotFound, ValidationFailed
from riso.shared.ids import IdGenerator
from riso.shared.ports import MailMessage

TEMPLATES_DIR = Path(__file__).resolve().parent / "mail_templates"


class MailOutboxRow(Base):
    __tablename__ = "mail_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    to_address: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    template: Mapped[str] = mapped_column(String(100))
    customer_id: Mapped[str | None] = mapped_column(String(36), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36))
    sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class OutboxMailSender:
    """Writes each message to the outbox on the given session; the caller commits."""

    def __init__(self, session: Session, clock: Clock, ids: IdGenerator) -> None:
        self._session = session
        self._clock = clock
        self._ids = ids

    def send(self, message: MailMessage) -> str:
        if "@" not in message.to:
            raise ValidationFailed.on("to", "not an email address", "email")
        row = MailOutboxRow(
            id=self._ids.new(),
            created_at=self._clock.now(),
            to_address=message.to,
            subject=message.subject,
            body=message.body,
            template=message.template,
            customer_id=message.customer_id,
            user_id=message.user_id,
            attempts=0,
        )
        self._session.add(row)
        return row.id


@dataclass(frozen=True, slots=True)
class RenderedMail:
    subject: str
    body: str
    template: str

    def to(
        self, address: str, *, customer_id: str | None = None, user_id: str | None = None
    ) -> MailMessage:
        return MailMessage(
            to=address,
            subject=self.subject,
            body=self.body,
            template=self.template,
            customer_id=customer_id,
            user_id=user_id,
        )


class MailTemplates:
    def __init__(self, directory: Path = TEMPLATES_DIR, locale: str = "sk") -> None:
        self._directory = directory
        self._locale = locale

    def render(self, name: str, **values: str) -> RenderedMail:
        path = self._directory / f"{name}.{self._locale}.txt"
        if not path.is_file():
            raise NotFound(f"no mail template {name}.{self._locale}")
        text = path.read_text(encoding="utf-8")
        head, separator, body = text.partition("\n\n")
        if not separator or not head.startswith("Subject: ") or "\n" in head:
            raise ValueError(f"mail template {name}: expected 'Subject: …', a blank line, a body")
        try:
            subject = Template(head.removeprefix("Subject: ")).substitute(values)
            rendered = Template(body).substitute(values)
        except KeyError as exc:
            raise ValueError(f"mail template {name}: no value for {exc.args[0]}") from exc
        return RenderedMail(subject=subject, body=rendered.rstrip("\n") + "\n", template=name)
