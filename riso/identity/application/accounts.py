"""Accounts by mail (plan §5.3, decisions 35–36): invitations, password resets, password and
login-email changes. Every mail goes to the outbox in the transaction of the change.

Tokens travel only in the mail; the answer to a reset request is the same whether or not the
address has an account; a failing token says only that the link is not valid or expired.
"""

from dataclasses import dataclass
from datetime import datetime

from riso.identity.application.auth import IdentityUnitOfWork, end_sessions
from riso.identity.application.ports import Links, TenancyDirectory, TokenGenerator
from riso.identity.application.views import UserView
from riso.identity.domain import (
    Email,
    MembershipScope,
    PasswordHasher,
    PasswordPolicy,
    Permission,
    Role,
    ScopeKind,
    Token,
    TokenKind,
    User,
    UserStatus,
    hash_token,
    invalid_token,
)
from riso.shared.clock import BRATISLAVA
from riso.shared.context import RequestContext
from riso.shared.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from riso.shared.values import clean_name


def _when(instant: datetime) -> str:
    """`18. 6. 2026 8:00`, in Bratislava, as the mails show it."""
    local = instant.astimezone(BRATISLAVA)
    return f"{local.day}. {local.month}. {local.year} {local.hour}:{local.minute:02d}"


def _issue(
    uow: IdentityUnitOfWork,
    tokens: TokenGenerator,
    kind: TokenKind,
    user_id: str,
    payload: dict[str, str] | None = None,
) -> tuple[str, Token]:
    """A new token of `kind` for the user; older unused ones of the kind stop working."""
    now = uow.clock.now()
    for old in uow.tokens.outstanding(user_id, kind):
        old.revoke(now)
        uow.tokens.save(old)
    secret = tokens.new_token()
    token = Token.issue(uow.ids.new(), kind, hash_token(secret), user_id, now, payload)
    uow.tokens.add(token)
    return secret, token


def _usable_token(uow: IdentityUnitOfWork, secret: str, kind: TokenKind) -> Token:
    token = uow.tokens.by_hash(hash_token(secret)) if secret else None
    if token is None or token.kind is not kind or not token.usable(uow.clock.now()):
        raise invalid_token()
    return token


def _account_words(user: User) -> list[str]:
    words = [user.name]
    if user.email is not None:
        words += [user.email.value, user.email.local_part]
    return words


# Invitations ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Invite:
    email: str
    name: str
    scope_kind: ScopeKind
    scope_id: str
    role: Role


@dataclass(frozen=True, slots=True)
class Invited:
    user: UserView
    new_account: bool
    """False when the address already had an account, which got the membership."""


def invite(
    ctx: RequestContext,
    uow: IdentityUnitOfWork,
    directory: TenancyDirectory,
    tokens: TokenGenerator,
    links: Links,
    cmd: Invite,
) -> Invited:
    """Invites a login into a customer (staff and admins) or a provider's staff (admins).

    An address without an account gets an invited account and a link to set its password.
    An address with an account gets the membership and a notice; its password stays (plan §2
    decision: no second user per address). Deleted accounts are restored by an admin first.
    """
    if cmd.scope_kind is ScopeKind.CUSTOMER:
        ctx.require(Permission.LOGINS_MANAGE, cmd.scope_id)
        customer = directory.customer(cmd.scope_id)
        if customer is None or not customer.active:
            raise NotFound(f"no customer {cmd.scope_id}")
        scope, scope_name = MembershipScope.customer(customer.id), customer.name
        customer_id: str | None = customer.id
        if cmd.role not in (Role.CUSTOMER_USER, Role.CUSTOMER_VIEWER):
            raise ValidationFailed.on("role", "not a customer role", "role_scope")
    elif cmd.scope_kind is ScopeKind.PROVIDER:
        ctx.require(Permission.PROVIDERS_MANAGE)
        provider = directory.provider(cmd.scope_id)
        if provider is None or not provider.active:
            raise NotFound(f"no provider {cmd.scope_id}")
        scope, scope_name, customer_id = MembershipScope.provider(provider.id), provider.name, None
        if cmd.role is not Role.PROVIDER_STAFF:
            raise ValidationFailed.on("role", "not a provider role", "role_scope")
    else:
        raise PermissionDenied("admins are not invited")
    email = Email.parse(cmd.email)
    name = clean_name(cmd.name)

    with uow:
        now = uow.clock.now()
        user = uow.users.find_by_email(email)
        new_account = user is None
        if user is None:
            user = User.invite(uow.ids.new(), name, email, now)
            user.grant(uow.ids.new(), scope, cmd.role, now)
            uow.users.add(user)
        elif user.status in (UserStatus.DELETED, UserStatus.PURGED):
            raise Conflict("the address belongs to a deleted account")
        else:
            user.grant(uow.ids.new(), scope, cmd.role, now)
            uow.users.save(user)
        if user.status is UserStatus.INVITED:
            secret, token = _issue(uow, tokens, TokenKind.INVITATION, user.id)
            uow.mailer.send(
                "invitation",
                email.value,
                user_id=user.id,
                customer_id=customer_id,
                name=user.name,
                scope=scope_name,
                link=links.invitation(secret),
                expires=_when(token.expires_at),
            )
        else:
            uow.mailer.send(
                "access_granted",
                (user.mail_address or email).value,
                user_id=user.id,
                customer_id=customer_id,
                name=user.name,
                scope=scope_name,
                link=links.login(),
            )
        uow.commit()
    return Invited(UserView.of(user), new_account)


def send_invitation_again(
    uow: IdentityUnitOfWork,
    tokens: TokenGenerator,
    links: Links,
    user: User,
    scope_name: str,
    customer_id: str | None,
) -> None:
    """Inside the caller's unit of work: a fresh invitation for a user who has not set a
    password yet (the earlier link stops working)."""
    assert user.email is not None
    secret, token = _issue(uow, tokens, TokenKind.INVITATION, user.id)
    uow.mailer.send(
        "invitation",
        user.email.value,
        user_id=user.id,
        customer_id=customer_id,
        name=user.name,
        scope=scope_name,
        link=links.invitation(secret),
        expires=_when(token.expires_at),
    )


def send_password_reset(
    uow: IdentityUnitOfWork, tokens: TokenGenerator, links: Links, user: User
) -> None:
    """Inside the caller's unit of work: a reset link to the user's mail address."""
    address = user.mail_address
    assert address is not None
    secret, token = _issue(uow, tokens, TokenKind.PASSWORD_RESET, user.id)
    uow.mailer.send(
        "password_reset",
        address.value,
        user_id=user.id,
        name=user.name,
        link=links.password_reset(secret),
        expires=_when(token.expires_at),
    )


@dataclass(frozen=True, slots=True)
class TokenInfo:
    kind: TokenKind
    name: str
    email: str
    """The login email, or for an email change the new address."""
    expires_at: datetime


def token_info(uow: IdentityUnitOfWork, secret: str) -> TokenInfo:
    """What a link is for, so its page can greet the user; `token_invalid` otherwise."""
    with uow:
        token = uow.tokens.by_hash(hash_token(secret)) if secret else None
        if token is None or not token.usable(uow.clock.now()):
            raise invalid_token()
        user = uow.users.get(token.user_id)
        if user.email is None:
            raise invalid_token()
        email = token.payload.get("email", user.email.value)
        return TokenInfo(token.kind, user.name, email, token.expires_at)


def accept_invitation(
    uow: IdentityUnitOfWork,
    hasher: PasswordHasher,
    policy: PasswordPolicy,
    secret: str,
    password: str,
) -> UserView:
    """Sets the invited user's password; the account becomes active."""
    with uow:
        token = _usable_token(uow, secret, TokenKind.INVITATION)
        user = uow.users.get(token.user_id)
        if user.status is not UserStatus.INVITED:
            raise invalid_token()
        policy.check(password, account=_account_words(user))
        now = uow.clock.now()
        user.set_password(hasher.hash(password), now)
        token.use(now)
        uow.tokens.save(token)
        uow.users.save(user)
        uow.commit()
    return UserView.of(user)


# Passwords --------------------------------------------------------------------------------


def request_password_reset(
    uow: IdentityUnitOfWork, tokens: TokenGenerator, links: Links, typed_email: str
) -> None:
    """Mails a reset link when the address is an active, unlocked account's login email.
    Answers the same in every case, so the caller learns nothing about accounts."""
    try:
        email = Email.parse(typed_email)
    except ValidationFailed:
        return
    with uow:
        user = uow.users.find_by_email(email)
        if user is None or not user.can_log_in:
            return
        send_password_reset(uow, tokens, links, user)
        uow.commit()


def reset_password(
    uow: IdentityUnitOfWork,
    hasher: PasswordHasher,
    policy: PasswordPolicy,
    secret: str,
    password: str,
) -> None:
    """Sets a new password from a reset link and ends every session of the user."""
    with uow:
        token = _usable_token(uow, secret, TokenKind.PASSWORD_RESET)
        user = uow.users.get(token.user_id)
        if not user.can_log_in:
            raise invalid_token()
        policy.check(password, account=_account_words(user))
        now = uow.clock.now()
        user.set_password(hasher.hash(password), now)
        token.use(now)
        uow.tokens.save(token)
        uow.users.save(user)
        end_sessions(uow, user.id)
        uow.commit()


def _require_own_credentials(ctx: RequestContext) -> str:
    """The personal credential endpoints refuse an impersonating admin (plan §5.4)."""
    if ctx.actor_id is None:
        raise PermissionDenied("not logged in")
    if ctx.impersonating:
        raise PermissionDenied("not while impersonating")
    return ctx.actor_id


def _verified(user: User, hasher: PasswordHasher, password: str, field: str) -> None:
    if user.password_hash is None or not hasher.verify(user.password_hash, password):
        raise ValidationFailed.on(field, "the password is not correct", "password_wrong")


def change_password(
    ctx: RequestContext,
    uow: IdentityUnitOfWork,
    hasher: PasswordHasher,
    policy: PasswordPolicy,
    links: Links,
    *,
    current_password: str,
    new_password: str,
    session_id: str,
) -> None:
    """Changes the caller's password, ends its other sessions, and mails a notice."""
    user_id = _require_own_credentials(ctx)
    with uow:
        user = uow.users.get(user_id)
        _verified(user, hasher, current_password, "current_password")
        policy.check(new_password, field="new_password", account=_account_words(user))
        now = uow.clock.now()
        user.set_password(hasher.hash(new_password), now)
        uow.users.save(user)
        end_sessions(uow, user.id, keep=session_id)
        address = user.mail_address
        if address is not None:
            uow.mailer.send(
                "password_changed",
                address.value,
                user_id=user.id,
                name=user.name,
                when=_when(now),
                link=links.login(),
            )
        uow.commit()


# The login email --------------------------------------------------------------------------


def request_email_change(
    ctx: RequestContext,
    uow: IdentityUnitOfWork,
    hasher: PasswordHasher,
    tokens: TokenGenerator,
    links: Links,
    *,
    new_email: str,
    current_password: str,
) -> None:
    """Mails a confirmation link to the new address and a notice to the old one. The login
    email changes only when the link is opened (plan §5.5: verified)."""
    user_id = _require_own_credentials(ctx)
    email = Email.parse(new_email, field="new_email")
    with uow:
        user = uow.users.get(user_id)
        _verified(user, hasher, current_password, "current_password")
        if email == user.email:
            raise ValidationFailed.on("new_email", "this is the current address", "unchanged")
        if uow.users.find_by_email(email) is not None:
            raise Conflict("the address is used by another account")
        secret, token = _issue(uow, tokens, TokenKind.EMAIL_CHANGE, user.id, {"email": email.value})
        uow.mailer.send(
            "email_change",
            email.value,
            user_id=user.id,
            name=user.name,
            link=links.email_change(secret),
            expires=_when(token.expires_at),
        )
        if user.mail_address is not None:
            uow.mailer.send(
                "email_change_notice",
                user.mail_address.value,
                user_id=user.id,
                name=user.name,
                new_email=email.value,
            )
        uow.commit()


def confirm_email_change(uow: IdentityUnitOfWork, secret: str) -> UserView:
    with uow:
        token = _usable_token(uow, secret, TokenKind.EMAIL_CHANGE)
        user = uow.users.get(token.user_id)
        email = Email.parse(token.payload.get("email", ""))
        other = uow.users.find_by_email(email)
        if other is not None and other.id != user.id:
            raise Conflict("the address is used by another account")
        user.change_email(email)
        token.use(uow.clock.now())
        uow.tokens.save(token)
        uow.users.save(user)
        uow.commit()
    return UserView.of(user)
