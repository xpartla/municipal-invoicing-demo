"""The views (DTOs) the identity use cases return."""

from dataclasses import dataclass
from datetime import datetime

from riso.identity.domain import Membership, Permission, Role, ScopeKind, Session, User, UserStatus


@dataclass(frozen=True, slots=True)
class MembershipView:
    id: str
    scope_kind: ScopeKind
    scope_id: str | None
    role: Role
    active: bool
    created_at: datetime
    deactivated_at: datetime | None

    @classmethod
    def of(cls, membership: Membership) -> "MembershipView":
        return cls(
            id=membership.id,
            scope_kind=membership.scope.kind,
            scope_id=membership.scope.id,
            role=membership.role,
            active=membership.active,
            created_at=membership.created_at,
            deactivated_at=membership.deactivated_at,
        )


@dataclass(frozen=True, slots=True)
class UserView:
    id: str
    name: str
    email: str | None
    notification_email: str | None
    status: UserStatus
    locked: bool
    created_at: datetime
    memberships: tuple[MembershipView, ...]

    @classmethod
    def of(cls, user: User) -> "UserView":
        return cls(
            id=user.id,
            name=user.name,
            email=user.email.value if user.email else None,
            notification_email=user.notification_email.value if user.notification_email else None,
            status=user.status,
            locked=user.locked_at is not None,
            created_at=user.created_at,
            memberships=tuple(MembershipView.of(m) for m in user.memberships),
        )


@dataclass(frozen=True, slots=True)
class SessionView:
    id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    """Whichever comes first: the idle or the absolute limit."""
    ip: str | None
    user_agent: str | None

    @classmethod
    def of(cls, session: Session) -> "SessionView":
        return cls(
            id=session.id,
            created_at=session.created_at,
            last_seen_at=session.last_seen_at,
            expires_at=min(session.expires_at, session.idle_expires_at),
            ip=session.ip,
            user_agent=session.user_agent,
        )


@dataclass(frozen=True, slots=True)
class ImpersonationView:
    real_user_id: str
    real_user_name: str
    reason: str
    started_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ScopeCapabilities:
    id: str
    name: str
    permissions: tuple[Permission, ...]


@dataclass(frozen=True, slots=True)
class CustomerCapabilities:
    id: str
    name: str
    ico: str
    provider_id: str | None
    permissions: tuple[Permission, ...]


@dataclass(frozen=True, slots=True)
class MeView:
    """What `GET /api/me` returns: the user, its memberships, what it may do where, and the
    customers it can open."""

    user: UserView
    session: SessionView
    impersonation: ImpersonationView | None
    platform: tuple[Permission, ...]
    providers: tuple[ScopeCapabilities, ...]
    customers: tuple[CustomerCapabilities, ...]
