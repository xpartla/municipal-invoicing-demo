"""Sessions and login attempts on SQLAlchemy, and the random token generator."""

import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from riso.identity.domain import LoginAttempts, Session
from riso.identity.infrastructure.orm import LoginAttemptRow, SessionRow
from riso.shared.errors import NotFound


class SecretsTokenGenerator:
    def new_token(self) -> str:
        return secrets.token_urlsafe(32)


class SqlSessionRepository:
    def __init__(self, session: OrmSession) -> None:
        self._db = session

    def add(self, session: Session) -> None:
        row = SessionRow(id=session.id)
        _write(session, row)
        self._db.add(row)

    def by_token_hash(self, token_hash: str) -> Session | None:
        row = self._db.scalars(
            select(SessionRow).where(SessionRow.token_hash == token_hash)
        ).first()
        return None if row is None else _read(row)

    def get(self, session_id: str) -> Session:
        row = self._db.get(SessionRow, session_id)
        if row is None:
            raise NotFound(f"no session {session_id}")
        return _read(row)

    def save(self, session: Session) -> None:
        row = self._db.get(SessionRow, session.id)
        if row is None:
            raise NotFound(f"no session {session.id}")
        _write(session, row)

    def active_of(self, user_id: str, now: datetime) -> list[Session]:
        rows = self._db.scalars(
            select(SessionRow)
            .where(
                SessionRow.user_id == user_id,
                SessionRow.revoked_at.is_(None),
                SessionRow.expires_at > now,
            )
            .order_by(SessionRow.created_at.desc(), SessionRow.id.desc())
        ).all()
        return [s for s in map(_read, rows) if s.is_valid(now)]

    def impersonating(self, user_id: str) -> list[Session]:
        rows = self._db.scalars(
            select(SessionRow).where(
                SessionRow.impersonated_user_id == user_id, SessionRow.revoked_at.is_(None)
            )
        ).all()
        return [_read(row) for row in rows]


def _write(session: Session, row: SessionRow) -> None:
    row.token_hash = session.token_hash
    row.user_id = session.user_id
    row.csrf_token = session.csrf_token
    row.created_at = session.created_at
    row.last_seen_at = session.last_seen_at
    row.expires_at = session.expires_at
    row.revoked_at = session.revoked_at
    row.ip = session.ip
    row.user_agent = session.user_agent
    row.impersonated_user_id = session.impersonated_user_id
    row.impersonation_reason = session.impersonation_reason
    row.impersonation_started_at = session.impersonation_started_at


def _read(row: SessionRow) -> Session:
    return Session(
        id=row.id,
        token_hash=row.token_hash,
        user_id=row.user_id,
        csrf_token=row.csrf_token,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        expires_at=row.expires_at,
        ip=row.ip,
        user_agent=row.user_agent,
        revoked_at=row.revoked_at,
        impersonated_user_id=row.impersonated_user_id,
        impersonation_reason=row.impersonation_reason,
        impersonation_started_at=row.impersonation_started_at,
    )


class SqlLoginAttemptRepository:
    def __init__(self, session: OrmSession) -> None:
        self._db = session

    def get(self, key: str) -> LoginAttempts:
        row = self._db.get(LoginAttemptRow, key)
        if row is None:
            return LoginAttempts(key)
        return LoginAttempts(key, row.failures, row.last_failure_at)

    def save(self, attempts: LoginAttempts) -> None:
        row = self._db.get(LoginAttemptRow, attempts.key)
        if attempts.failures == 0:
            if row is not None:
                self._db.delete(row)
            return
        if row is None:
            row = LoginAttemptRow(key=attempts.key)
            self._db.add(row)
        row.failures = attempts.failures
        row.last_failure_at = attempts.last_failure_at
