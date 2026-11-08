"""Managing users and logins (plan §5.2, §5.5, §5.6, §10.8–10.9).

- The caller's own profile: name and notification email.
- A customer's logins, by its provider's staff and admins: deactivate and reactivate the
  membership (plan §2 decision 49), send a reset link (or a new invitation).
- A provider's staff, by admins: take a member off the provider.
- Any account, by admins: lock and unlock, force a logout, delete, restore and purge (which
  anonymises, decision 51), and the list of every user.

Staff manage the logins of their customers but never an admin's account.
"""

from dataclasses import dataclass

from riso.identity.application.accounts import send_invitation_again, send_password_reset
from riso.identity.application.auth import IdentityUnitOfWork, end_sessions
from riso.identity.application.ports import Links, TenancyDirectory, TokenGenerator
from riso.identity.application.views import UserView
from riso.identity.domain import (
    Email,
    MembershipScope,
    Permission,
    TokenKind,
    User,
    UserStatus,
)
from riso.shared.context import RequestContext
from riso.shared.errors import InvalidState, NotFound, PermissionDenied
from riso.shared.values import clean_name


def _audit(
    ctx: RequestContext, uow: IdentityUnitOfWork, action: str, user: User, **extra: object
) -> None:
    customer_id = extra.pop("customer_id", None)
    uow.audit.record(
        ctx,
        action,
        target_type="user",
        target_id=user.id,
        customer_id=customer_id if isinstance(customer_id, str) else None,
        details=extra or None,
    )


# The caller's own profile ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProfileChange:
    name: str | None = None
    """None keeps the name."""
    notification_email: str | None = None
    set_notification_email: bool = False
    """Whether `notification_email` is meant: None or "" then clears it."""


def update_profile(ctx: RequestContext, uow: IdentityUnitOfWork, change: ProfileChange) -> UserView:
    """The caller's name and notification email. Allowed while impersonating, and then
    audited with both IDs; the login email and the password have their own flows."""
    if ctx.actor_id is None:
        raise PermissionDenied("not logged in")
    name = clean_name(change.name) if change.name is not None else None
    email = (
        Email.parse(change.notification_email, field="notification_email")
        if change.set_notification_email and change.notification_email
        else None
    )
    with uow:
        user = uow.users.get(ctx.actor_id)
        fields = []
        if name is not None and name != user.name:
            user.rename(name)
            fields.append("name")
        if change.set_notification_email and email != user.notification_email:
            user.set_notification_email(email)
            fields.append("notification_email")
        uow.users.save(user)
        _audit(ctx, uow, "user.profile_updated", user, fields=fields)
        uow.commit()
    return UserView.of(user)


# A customer's logins -----------------------------------------------------------------------


def _login(uow: IdentityUnitOfWork, ctx: RequestContext, customer_id: str, user_id: str) -> User:
    """The user, who must have a membership in the customer (404 otherwise). Only an admin
    may manage an admin's account."""
    user = uow.users.get(user_id)
    if user.membership_in(MembershipScope.customer(customer_id)) is None:
        raise NotFound(f"no login {user_id} in customer {customer_id}")
    if user.is_admin and not ctx.allows(Permission.USERS_ADMINISTER):
        raise PermissionDenied("an admin's account is managed by admins")
    return user


def deactivate_login(
    ctx: RequestContext, uow: IdentityUnitOfWork, customer_id: str, user_id: str
) -> UserView:
    ctx.require(Permission.LOGINS_MANAGE, customer_id)
    with uow:
        user = _login(uow, ctx, customer_id, user_id)
        user.deactivate_membership(MembershipScope.customer(customer_id), uow.clock.now())
        uow.users.save(user)
        _audit(ctx, uow, "login.deactivated", user, customer_id=customer_id)
        uow.commit()
    return UserView.of(user)


def reactivate_login(
    ctx: RequestContext, uow: IdentityUnitOfWork, customer_id: str, user_id: str
) -> UserView:
    ctx.require(Permission.LOGINS_MANAGE, customer_id)
    with uow:
        user = _login(uow, ctx, customer_id, user_id)
        user.reactivate_membership(MembershipScope.customer(customer_id))
        uow.users.save(user)
        _audit(ctx, uow, "login.reactivated", user, customer_id=customer_id)
        uow.commit()
    return UserView.of(user)


def send_login_link(
    ctx: RequestContext,
    uow: IdentityUnitOfWork,
    directory: TenancyDirectory,
    tokens: TokenGenerator,
    links: Links,
    customer_id: str,
    user_id: str,
) -> TokenKind:
    """A reset link for an account with a password, or a new invitation for one still
    invited. Staff cannot set or see passwords (plan §2 decision 5)."""
    ctx.require(Permission.LOGINS_MANAGE, customer_id)
    customer = directory.customer(customer_id)
    if customer is None:
        raise NotFound(f"no customer {customer_id}")
    with uow:
        user = _login(uow, ctx, customer_id, user_id)
        if user.status is UserStatus.INVITED:
            send_invitation_again(uow, tokens, links, user, customer.name, customer_id)
            kind = TokenKind.INVITATION
        elif user.can_log_in:
            send_password_reset(uow, tokens, links, user)
            kind = TokenKind.PASSWORD_RESET
        else:
            raise InvalidState(f"user {user.id} is locked or deleted")
        _audit(ctx, uow, "login.link_sent", user, customer_id=customer_id, kind=kind.value)
        uow.commit()
    return kind


# A provider's staff -----------------------------------------------------------------------


def remove_staff(
    ctx: RequestContext, uow: IdentityUnitOfWork, provider_id: str, user_id: str
) -> UserView:
    """Takes the user off the provider; inviting the address again brings them back."""
    ctx.require(Permission.PROVIDERS_MANAGE)
    with uow:
        user = uow.users.get(user_id)
        scope = MembershipScope.provider(provider_id)
        if user.membership_in(scope) is None:
            raise NotFound(f"user {user_id} is not staff of provider {provider_id}")
        user.remove_membership(scope)
        uow.users.save(user)
        _audit(ctx, uow, "staff.removed", user, provider_id=provider_id)
        uow.commit()
    return UserView.of(user)


# Any account, by admins ---------------------------------------------------------------------


def _target(ctx: RequestContext, uow: IdentityUnitOfWork, user_id: str) -> User:
    if user_id == ctx.actor_id:
        raise InvalidState("an admin cannot do this to their own account")
    return uow.users.get(user_id)


def lock_user(ctx: RequestContext, uow: IdentityUnitOfWork, user_id: str) -> UserView:
    ctx.require(Permission.USERS_ADMINISTER)
    with uow:
        user = _target(ctx, uow, user_id)
        user.lock(uow.clock.now())
        uow.users.save(user)
        ended = end_sessions(uow, user.id)
        _audit(ctx, uow, "user.locked", user, sessions=ended)
        uow.commit()
    return UserView.of(user)


def unlock_user(ctx: RequestContext, uow: IdentityUnitOfWork, user_id: str) -> UserView:
    ctx.require(Permission.USERS_ADMINISTER)
    with uow:
        user = uow.users.get(user_id)
        user.unlock()
        uow.users.save(user)
        _audit(ctx, uow, "user.unlocked", user)
        uow.commit()
    return UserView.of(user)


def force_logout(ctx: RequestContext, uow: IdentityUnitOfWork, user_id: str) -> int:
    ctx.require(Permission.USERS_ADMINISTER)
    with uow:
        user = _target(ctx, uow, user_id)
        ended = end_sessions(uow, user.id)
        _audit(ctx, uow, "user.logged_out", user, sessions=ended)
        uow.commit()
    return ended


def delete_user(ctx: RequestContext, uow: IdentityUnitOfWork, user_id: str) -> UserView:
    ctx.require(Permission.USERS_DELETE)
    with uow:
        user = _target(ctx, uow, user_id)
        user.delete(uow.clock.now())
        uow.users.save(user)
        end_sessions(uow, user.id)
        _audit(ctx, uow, "user.deleted", user)
        uow.commit()
    return UserView.of(user)


def restore_user(ctx: RequestContext, uow: IdentityUnitOfWork, user_id: str) -> UserView:
    ctx.require(Permission.USERS_DELETE)
    with uow:
        user = uow.users.get(user_id)
        user.restore()
        uow.users.save(user)
        _audit(ctx, uow, "user.restored", user)
        uow.commit()
    return UserView.of(user)


def purge_user(ctx: RequestContext, uow: IdentityUnitOfWork, user_id: str) -> UserView:
    """Anonymises a deleted user (plan §2 decision 51); outstanding links stop working."""
    ctx.require(Permission.USERS_DELETE)
    with uow:
        user = _target(ctx, uow, user_id)
        now = uow.clock.now()
        user.purge(now)
        uow.users.save(user)
        for kind in TokenKind:
            for token in uow.tokens.outstanding(user.id, kind):
                token.revoke(now)
                uow.tokens.save(token)
        _audit(ctx, uow, "user.purged", user)
        uow.commit()
    return UserView.of(user)


def list_users(
    ctx: RequestContext,
    uow: IdentityUnitOfWork,
    *,
    query: str | None = None,
    include_deleted: bool = False,
) -> list[UserView]:
    ctx.require(Permission.USERS_ADMINISTER)
    with uow:
        return [
            UserView.of(u) for u in uow.users.find(query=query, include_deleted=include_deleted)
        ]
