"""Logging in and out, resolving a session, and what `GET /api/me` shows (plan §5.3).

A failed login says only that it failed: an unknown email, a wrong password, and an account
that is invited, locked or deleted look the same, and an unknown email costs as much time as
a wrong password. Failures are throttled per account and per client address
(`riso.identity.domain.throttle`).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from riso.identity.application.access import Grant, MembershipPolicy
from riso.identity.application.ports import TenancyDirectory, TokenGenerator
from riso.identity.application.views import (
    CustomerCapabilities,
    ImpersonationView,
    MeView,
    ScopeCapabilities,
    SessionView,
    UserView,
)
from riso.identity.domain import (
    Email,
    LoginAttemptRepository,
    PasswordHasher,
    Session,
    SessionRepository,
    TokenRepository,
    User,
    UserRepository,
    account_key,
    hash_token,
    ip_key,
)
from riso.shared.errors import Throttled, Unauthenticated, ValidationFailed
from riso.shared.ports import Mailer
from riso.shared.uow import UnitOfWork

TIMING_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$/JfyBWUkCo7/oxKvITBy+g"
    "$U/cT2kWXQubflkXAw4wsFhh1rvKZPwI1AoK4GyC8Z+k"
)
"""A hash checked when there is no account, so the answer takes as long as a wrong password."""


class IdentityUnitOfWork(UnitOfWork, Protocol):
    @property
    def users(self) -> UserRepository: ...

    @property
    def sessions(self) -> SessionRepository: ...

    @property
    def login_attempts(self) -> LoginAttemptRepository: ...

    @property
    def tokens(self) -> TokenRepository: ...

    @property
    def mailer(self) -> Mailer: ...


IdentityUnitsOfWork = Callable[[bool], IdentityUnitOfWork]
"""Makes an identity unit of work; the argument asks for the write lock up front."""


@dataclass(frozen=True, slots=True)
class Login:
    email: str
    password: str
    ip: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class LoggedIn:
    token: str
    """The session token for the cookie; the server keeps only its hash."""
    csrf_token: str
    session_id: str
    user_id: str


def login(
    uow: IdentityUnitOfWork, hasher: PasswordHasher, tokens: TokenGenerator, cmd: Login
) -> LoggedIn:
    """Raises `Throttled` while the account or the address is blocked, `Unauthenticated` when
    the login fails."""
    with uow:
        now = uow.clock.now()
        counters = [uow.login_attempts.get(account_key(cmd.email))]
        if cmd.ip:
            counters.append(uow.login_attempts.get(ip_key(cmd.ip)))
        blocked = [until for c in counters if (until := c.blocked_until(now)) is not None]
        if blocked:
            raise Throttled("too many failed logins", int((max(blocked) - now).total_seconds()) + 1)

        user = _user_by_email(uow, cmd.email)
        if user is not None and user.password_hash is not None:
            matches = hasher.verify(user.password_hash, cmd.password)
        else:
            hasher.verify(TIMING_HASH, cmd.password)
            matches = False
        if user is None or not matches or not user.can_log_in:
            for counter in counters:
                counter.record_failure(now)
                uow.login_attempts.save(counter)
            uow.commit()
            raise Unauthenticated("login failed")

        for counter in counters:
            counter.reset()
            uow.login_attempts.save(counter)
        assert user.password_hash is not None  # can_log_in
        if hasher.needs_rehash(user.password_hash):
            user.replace_hash(hasher.hash(cmd.password))
            uow.users.save(user)
        token, csrf = tokens.new_token(), tokens.new_token()
        session = Session.start(
            uow.ids.new(),
            hash_token(token),
            csrf,
            user.id,
            now,
            ip=cmd.ip,
            user_agent=cmd.user_agent,
        )
        uow.sessions.add(session)
        uow.commit()
    return LoggedIn(token=token, csrf_token=csrf, session_id=session.id, user_id=user.id)


def _user_by_email(uow: IdentityUnitOfWork, typed: str) -> User | None:
    try:
        email = Email.parse(typed)
    except ValidationFailed:
        return None
    return uow.users.find_by_email(email)


# Resolving a session ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Authenticated:
    """A valid session and whom it acts as."""

    session_id: str
    csrf_token: str
    session: SessionView
    user: UserView
    """The principal: the impersonated user while impersonating, else the one logged in."""
    real_user: UserView | None
    """The admin behind an impersonation; None otherwise."""
    impersonation: ImpersonationView | None
    grants: tuple[Grant, ...]
    """The principal's active memberships."""

    @property
    def actor_id(self) -> str:
        return self.user.id

    @property
    def real_actor_id(self) -> str | None:
        return self.real_user.id if self.real_user else None


def authenticate(uows: IdentityUnitsOfWork, token: str) -> Authenticated | None:
    """The session of a cookie's token, or None when it is unknown, ended, expired, or its
    user can no longer log in. Most requests only read; the time of the last request is
    written once a minute, and an impersonation past its limit is ended."""
    with uows(False) as uow:
        found, dirty = _resolve(uow, token)
    if not dirty:
        return found
    with uows(True) as uow:
        found, dirty = _resolve(uow, token)
        if dirty:
            uow.commit()
    return found


def _resolve(uow: IdentityUnitOfWork, token: str) -> tuple[Authenticated | None, bool]:
    """The session, and whether it changed and must be saved (the caller commits)."""
    now = uow.clock.now()
    session = uow.sessions.by_token_hash(hash_token(token))
    if session is None or not session.is_valid(now):
        return None, False
    user = uow.users.get(session.user_id)
    if not user.can_log_in:
        return None, False
    dirty = session.touch(now)

    principal, impersonation = user, None
    if session.impersonated_user_id is not None:
        target = uow.users.get(session.impersonated_user_id)
        if session.impersonation_expired(now) or not target.can_log_in or target.is_admin:
            session.end_impersonation()
            dirty = True
        else:
            assert session.impersonation_started_at is not None
            assert session.impersonation_expires_at is not None
            principal = target
            impersonation = ImpersonationView(
                real_user_id=user.id,
                real_user_name=user.name,
                reason=session.impersonation_reason or "",
                started_at=session.impersonation_started_at,
                expires_at=session.impersonation_expires_at,
            )
    if dirty:
        uow.sessions.save(session)
    grants = tuple(Grant(m.scope.kind, m.scope.id, m.role) for m in principal.active_memberships())
    return (
        Authenticated(
            session_id=session.id,
            csrf_token=session.csrf_token,
            session=SessionView.of(session),
            user=UserView.of(principal),
            real_user=UserView.of(user) if impersonation else None,
            impersonation=impersonation,
            grants=grants,
        ),
        dirty,
    )


# Logging out ------------------------------------------------------------------------------


def logout(uow: IdentityUnitOfWork, session_id: str) -> None:
    with uow:
        session = uow.sessions.get(session_id)
        if session.revoked_at is None:
            session.revoke(uow.clock.now())
            uow.sessions.save(session)
        uow.commit()


def end_sessions(uow: IdentityUnitOfWork, user_id: str, *, keep: str | None = None) -> int:
    """Inside the caller's unit of work: ends the user's sessions (all but `keep`) and the
    impersonations of the user, and returns how many sessions ended. Used by "log out
    everywhere", a password change, locking, deleting and forcing a logout."""
    now = uow.clock.now()
    ended = 0
    for session in uow.sessions.active_of(user_id, now):
        if session.id != keep:
            session.revoke(now)
            uow.sessions.save(session)
            ended += 1
    for session in uow.sessions.impersonating(user_id):
        session.end_impersonation()
        uow.sessions.save(session)
    return ended


def logout_everywhere(uow: IdentityUnitOfWork, user_id: str) -> int:
    with uow:
        ended = end_sessions(uow, user_id)
        uow.commit()
    return ended


def list_sessions(uow: IdentityUnitOfWork, user_id: str) -> list[SessionView]:
    with uow:
        return [SessionView.of(s) for s in uow.sessions.active_of(user_id, uow.clock.now())]


# What the caller may do -------------------------------------------------------------------


def me(auth: Authenticated, policy: MembershipPolicy, directory: TenancyDirectory) -> MeView:
    providers = tuple(
        ScopeCapabilities(p.id, p.name, tuple(sorted(policy.in_provider(p.id))))
        for p in directory.providers(policy.provider_ids)
        if p.active
    )
    customers = tuple(
        CustomerCapabilities(
            id=c.id,
            name=c.name,
            ico=c.ico,
            provider_id=c.provider_id,
            permissions=tuple(sorted(policy.in_customer(c.id))),
        )
        for c in policy.accessible_customers()
    )
    return MeView(
        user=auth.user,
        session=auth.session,
        impersonation=auth.impersonation,
        platform=tuple(sorted(policy.on_platform())),
        providers=providers,
        customers=customers,
    )
