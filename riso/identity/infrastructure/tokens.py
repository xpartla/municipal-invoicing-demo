"""Mail tokens on SQLAlchemy."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from riso.identity.domain import Token, TokenKind
from riso.identity.infrastructure.orm import TokenRow
from riso.shared.errors import NotFound


class SqlTokenRepository:
    def __init__(self, session: Session) -> None:
        self._db = session

    def add(self, token: Token) -> None:
        row = TokenRow(id=token.id)
        _write(token, row)
        self._db.add(row)

    def by_hash(self, token_hash: str) -> Token | None:
        row = self._db.scalars(select(TokenRow).where(TokenRow.token_hash == token_hash)).first()
        return None if row is None else _read(row)

    def save(self, token: Token) -> None:
        row = self._db.get(TokenRow, token.id)
        if row is None:
            raise NotFound(f"no token {token.id}")
        _write(token, row)

    def outstanding(self, user_id: str, kind: TokenKind) -> list[Token]:
        rows = self._db.scalars(
            select(TokenRow).where(
                TokenRow.user_id == user_id,
                TokenRow.kind == kind.value,
                TokenRow.used_at.is_(None),
                TokenRow.revoked_at.is_(None),
            )
        ).all()
        return [_read(row) for row in rows]


def _write(token: Token, row: TokenRow) -> None:
    row.kind = token.kind.value
    row.token_hash = token.token_hash
    row.user_id = token.user_id
    row.created_at = token.created_at
    row.expires_at = token.expires_at
    row.used_at = token.used_at
    row.revoked_at = token.revoked_at
    row.payload = dict(token.payload)


def _read(row: TokenRow) -> Token:
    return Token(
        id=row.id,
        kind=TokenKind(row.kind),
        token_hash=row.token_hash,
        user_id=row.user_id,
        created_at=row.created_at,
        expires_at=row.expires_at,
        used_at=row.used_at,
        revoked_at=row.revoked_at,
        payload=dict(row.payload),
    )
