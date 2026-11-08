"""Request and response models of the identity API."""

from datetime import datetime

from pydantic import BaseModel, Field

from riso.identity.application.views import (
    MembershipView,
    MeView,
    SessionView,
    UserView,
)
from riso.identity.domain import Permission, Role, ScopeKind, TokenKind, UserStatus


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


class MembershipOut(BaseModel):
    id: str
    scope_kind: ScopeKind
    scope_id: str | None
    role: Role
    active: bool

    @classmethod
    def of(cls, view: MembershipView) -> "MembershipOut":
        return cls(
            id=view.id,
            scope_kind=view.scope_kind,
            scope_id=view.scope_id,
            role=view.role,
            active=view.active,
        )


class UserOut(BaseModel):
    id: str
    name: str
    email: str | None
    notification_email: str | None
    status: UserStatus
    locked: bool
    memberships: list[MembershipOut]

    @classmethod
    def of(cls, view: UserView) -> "UserOut":
        return cls(
            id=view.id,
            name=view.name,
            email=view.email,
            notification_email=view.notification_email,
            status=view.status,
            locked=view.locked,
            memberships=[MembershipOut.of(m) for m in view.memberships],
        )


class SessionOut(BaseModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip: str | None
    user_agent: str | None
    current: bool = False

    @classmethod
    def of(cls, view: SessionView, current_id: str | None = None) -> "SessionOut":
        return cls(
            id=view.id,
            created_at=view.created_at,
            last_seen_at=view.last_seen_at,
            expires_at=view.expires_at,
            ip=view.ip,
            user_agent=view.user_agent,
            current=view.id == current_id,
        )


class ImpersonationOut(BaseModel):
    real_user_id: str
    real_user_name: str
    reason: str
    started_at: datetime
    expires_at: datetime


class ScopeOut(BaseModel):
    id: str
    name: str
    permissions: list[Permission]


class CustomerAccessOut(BaseModel):
    id: str
    name: str
    ico: str
    provider_id: str | None
    permissions: list[Permission]


class MeOut(BaseModel):
    """The caller, its memberships, and its capabilities: what it may do on the platform, in
    each of its providers, and in each customer it can open."""

    user: UserOut
    session: SessionOut
    impersonation: ImpersonationOut | None
    platform: list[Permission]
    providers: list[ScopeOut]
    customers: list[CustomerAccessOut]

    @classmethod
    def of(cls, view: MeView) -> "MeOut":
        i = view.impersonation
        return cls(
            user=UserOut.of(view.user),
            session=SessionOut.of(view.session, view.session.id),
            impersonation=(
                ImpersonationOut(
                    real_user_id=i.real_user_id,
                    real_user_name=i.real_user_name,
                    reason=i.reason,
                    started_at=i.started_at,
                    expires_at=i.expires_at,
                )
                if i
                else None
            ),
            platform=list(view.platform),
            providers=[
                ScopeOut(id=p.id, name=p.name, permissions=list(p.permissions))
                for p in view.providers
            ],
            customers=[
                CustomerAccessOut(
                    id=c.id,
                    name=c.name,
                    ico=c.ico,
                    provider_id=c.provider_id,
                    permissions=list(c.permissions),
                )
                for c in view.customers
            ],
        )


class TokenIn(BaseModel):
    token: str = Field(max_length=200)


class TokenInfoOut(BaseModel):
    kind: TokenKind
    name: str
    email: str
    expires_at: datetime


class SetPasswordIn(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(max_length=1024)


class ResetRequestIn(BaseModel):
    email: str = Field(max_length=320)


class AcceptedOut(BaseModel):
    detail: str


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)


class EmailChangeIn(BaseModel):
    new_email: str = Field(max_length=320)
    current_password: str = Field(max_length=1024)


class ImpersonateIn(BaseModel):
    reason: str = Field(max_length=500)


class ProfileIn(BaseModel):
    """Only the fields sent change; `notification_email` null or "" clears it."""

    name: str | None = Field(default=None, max_length=200)
    notification_email: str | None = Field(default=None, max_length=320)


class InviteIn(BaseModel):
    email: str = Field(max_length=320)
    name: str = Field(max_length=200)
    role: Role = Role.CUSTOMER_USER


class StaffIn(BaseModel):
    email: str = Field(max_length=320)
    name: str = Field(max_length=200)


class InvitedOut(BaseModel):
    user: UserOut
    new_account: bool


class LinkSentOut(BaseModel):
    kind: TokenKind


class UserPageOut(BaseModel):
    items: list[UserOut]
    total: int
