"""The identity API: logging in and out, and the caller's own account (`/api/auth/…`,
`/api/me/…`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from riso.api.deps import (
    AnyCaller,
    Caller,
    PersonalCaller,
    SelfCaller,
    ServicesDep,
    check_csrf,
    clear_session_cookies,
    customer_context,
    platform_context,
    set_session_cookies,
)
from riso.identity.api.models import (
    AcceptedOut,
    ChangePasswordIn,
    EmailChangeIn,
    ImpersonateIn,
    InvitedOut,
    InviteIn,
    LinkSentOut,
    LoginIn,
    MeOut,
    ProfileIn,
    ResetRequestIn,
    SessionOut,
    SetPasswordIn,
    StaffIn,
    TokenIn,
    TokenInfoOut,
    UserOut,
    UserPageOut,
)
from riso.identity.application.accounts import (
    Invite,
    accept_invitation,
    change_password,
    confirm_email_change,
    invite,
    request_email_change,
    request_password_reset,
    reset_password,
    token_info,
)
from riso.identity.application.auth import (
    Login,
    authenticate,
    list_sessions,
    login,
    logout,
    logout_everywhere,
    me,
)
from riso.identity.application.impersonation import end_impersonation, start_impersonation
from riso.identity.application.users import (
    ProfileChange,
    deactivate_login,
    delete_user,
    force_logout,
    list_users,
    lock_user,
    purge_user,
    reactivate_login,
    remove_staff,
    restore_user,
    send_login_link,
    unlock_user,
    update_profile,
)
from riso.identity.domain import Permission, Role, ScopeKind
from riso.shared.errors import Unauthenticated

router = APIRouter(prefix="/api", dependencies=[Depends(check_csrf)], tags=["identity"])


@router.post("/auth/login", name="auth.login")
def login_route(
    body: LoginIn, request: Request, response: Response, caller: AnyCaller, services: ServicesDep
) -> MeOut:
    """Logs in with the login email and password. Sets the session and CSRF cookies. Answers
    401 for any failure and 429 (with `Retry-After`) while throttled."""
    done = login(
        caller.ctx,
        services.uow(),
        services.hasher,
        services.tokens,
        Login(
            email=body.email,
            password=body.password,
            ip=caller.ctx.ip,
            user_agent=request.headers.get("user-agent"),
        ),
    )
    set_session_cookies(response, services, done.token, done.csrf_token)
    auth = authenticate(services.uow, done.token, caller.ctx)
    if auth is None:  # pragma: no cover - the session was made a moment ago
        raise Unauthenticated("login failed")
    return MeOut.of(me(auth, services.policy(auth.grants), services.directory))


@router.post("/auth/logout", name="auth.logout", status_code=204)
def logout_route(response: Response, caller: SelfCaller, services: ServicesDep) -> None:
    """Ends this session."""
    logout(caller.ctx, services.uow(), caller.required().session_id)
    clear_session_cookies(response, services)


@router.post("/auth/logout-all", name="auth.logout_all", status_code=204)
def logout_all_route(response: Response, caller: PersonalCaller, services: ServicesDep) -> None:
    """Ends every session of the caller, this one included. Refused while impersonating."""
    logout_everywhere(caller.ctx, services.uow(), caller.required().actor_id)
    clear_session_cookies(response, services)


@router.get("/me", name="me.get")
def me_route(caller: SelfCaller, services: ServicesDep) -> MeOut:
    """The caller, its memberships and capabilities, and the customers it can open."""
    auth = caller.required()
    assert caller.policy is not None
    return MeOut.of(me(auth, caller.policy, services.directory))


@router.get("/me/sessions", name="me.sessions")
def sessions_route(caller: SelfCaller, services: ServicesDep) -> list[SessionOut]:
    """The caller's active sessions, newest first."""
    auth = caller.required()
    return [
        SessionOut.of(view, auth.session_id)
        for view in list_sessions(services.uow(immediate=False), auth.actor_id)
    ]


# Links from mail ---------------------------------------------------------------------------


@router.post("/auth/token-info", name="auth.token_info")
def token_info_route(body: TokenIn, caller: AnyCaller, services: ServicesDep) -> TokenInfoOut:
    """What a link from a mail is for (invitation, reset, email change) and for whom; 422
    with `token_invalid` when it is not valid or has expired."""
    info = token_info(services.uow(immediate=False), body.token)
    return TokenInfoOut(
        kind=info.kind, name=info.name, email=info.email, expires_at=info.expires_at
    )


@router.post("/auth/invitation/accept", name="auth.accept_invitation", status_code=204)
def accept_invitation_route(body: SetPasswordIn, caller: AnyCaller, services: ServicesDep) -> None:
    """Sets the password of an invited account from the invitation link."""
    accept_invitation(
        caller.ctx,
        services.uow(),
        services.hasher,
        services.password_policy,
        body.token,
        body.password,
    )


@router.post("/auth/password-reset", name="auth.request_reset", status_code=202)
def request_reset_route(
    body: ResetRequestIn, caller: AnyCaller, services: ServicesDep
) -> AcceptedOut:
    """Mails a reset link if the address has an account. The answer is always the same."""
    request_password_reset(caller.ctx, services.uow(), services.tokens, services.links, body.email)
    return AcceptedOut(detail="if the address has an account, a link was sent to it")


@router.post("/auth/password-reset/complete", name="auth.reset_password", status_code=204)
def reset_password_route(body: SetPasswordIn, caller: AnyCaller, services: ServicesDep) -> None:
    """Sets a new password from a reset link and ends every session of the account."""
    reset_password(
        caller.ctx,
        services.uow(),
        services.hasher,
        services.password_policy,
        body.token,
        body.password,
    )


@router.post("/auth/email-change/confirm", name="auth.confirm_email_change", status_code=204)
def confirm_email_route(body: TokenIn, caller: AnyCaller, services: ServicesDep) -> None:
    """Makes the new address the login email, from the link mailed to it."""
    confirm_email_change(caller.ctx, services.uow(), body.token)


# The caller's credentials ------------------------------------------------------------------


@router.post("/me/password", name="me.change_password", status_code=204)
def change_password_route(
    body: ChangePasswordIn, caller: PersonalCaller, services: ServicesDep
) -> None:
    """Changes the password and ends the caller's other sessions. Refused while
    impersonating."""
    change_password(
        caller.ctx,
        services.uow(),
        services.hasher,
        services.password_policy,
        services.links,
        current_password=body.current_password,
        new_password=body.new_password,
        session_id=caller.required().session_id,
    )


@router.post("/me/email-change", name="me.request_email_change", status_code=202)
def email_change_route(
    body: EmailChangeIn, caller: PersonalCaller, services: ServicesDep
) -> AcceptedOut:
    """Mails a confirmation link to the new address. Refused while impersonating."""
    request_email_change(
        caller.ctx,
        services.uow(),
        services.hasher,
        services.tokens,
        services.links,
        new_email=body.new_email,
        current_password=body.current_password,
    )
    return AcceptedOut(detail="a confirmation link was sent to the new address")


# Impersonation -----------------------------------------------------------------------------


@router.post("/admin/users/{user_id}/impersonate", name="users.impersonate", status_code=204)
def impersonate_route(
    caller: Annotated[Caller, Depends(platform_context(Permission.USERS_IMPERSONATE))],
    services: ServicesDep,
    user_id: str,
    body: ImpersonateIn,
) -> None:
    """Starts acting as the user in this session, for at most 60 minutes. Needs a reason;
    another admin cannot be the target."""
    start_impersonation(
        caller.ctx,
        services.uow(),
        session_id=caller.required().session_id,
        user_id=user_id,
        reason=body.reason,
    )


@router.post("/me/impersonation/end", name="me.end_impersonation", status_code=204)
def end_impersonation_route(caller: SelfCaller, services: ServicesDep) -> None:
    """Ends the impersonation; the session is the admin's again."""
    end_impersonation(caller.ctx, services.uow(), session_id=caller.required().session_id)


# The caller's profile ----------------------------------------------------------------------


@router.patch("/me", name="me.update")
def update_me_route(caller: SelfCaller, services: ServicesDep, body: ProfileIn) -> UserOut:
    """The caller's name and notification email (allowed while impersonating, audited with
    both IDs)."""
    sent = body.model_fields_set
    change = ProfileChange(
        name=body.name if "name" in sent else None,
        notification_email=body.notification_email,
        set_notification_email="notification_email" in sent,
    )
    return UserOut.of(update_profile(caller.ctx, services.uow(), change))


# A customer's logins (staff of its provider, admins) ---------------------------------------

LoginManager = Annotated[Caller, Depends(customer_context(Permission.LOGINS_MANAGE))]


@router.post("/customers/{customer_id}/logins", name="logins.invite", status_code=201)
def invite_login_route(
    caller: LoginManager, services: ServicesDep, customer_id: str, body: InviteIn
) -> InvitedOut:
    """Invites a login (Používateľ or Iba na čítanie) by mail; an existing account gets the
    access and a notice."""
    done = invite(
        caller.ctx,
        services.uow(),
        services.directory,
        services.tokens,
        services.links,
        Invite(body.email, body.name, ScopeKind.CUSTOMER, customer_id, body.role),
    )
    return InvitedOut(user=UserOut.of(done.user), new_account=done.new_account)


@router.post("/customers/{customer_id}/logins/{user_id}/deactivate", name="logins.deactivate")
def deactivate_login_route(
    caller: LoginManager, services: ServicesDep, customer_id: str, user_id: str
) -> UserOut:
    """Removes the login's access to this customer; the account stays."""
    return UserOut.of(deactivate_login(caller.ctx, services.uow(), customer_id, user_id))


@router.post("/customers/{customer_id}/logins/{user_id}/reactivate", name="logins.reactivate")
def reactivate_login_route(
    caller: LoginManager, services: ServicesDep, customer_id: str, user_id: str
) -> UserOut:
    return UserOut.of(reactivate_login(caller.ctx, services.uow(), customer_id, user_id))


@router.post("/customers/{customer_id}/logins/{user_id}/reset-link", name="logins.send_link")
def send_link_route(
    caller: LoginManager, services: ServicesDep, customer_id: str, user_id: str
) -> LinkSentOut:
    """Mails a password reset link, or a new invitation to a login still invited."""
    kind = send_login_link(
        caller.ctx,
        services.uow(),
        services.directory,
        services.tokens,
        services.links,
        customer_id,
        user_id,
    )
    return LinkSentOut(kind=kind)


# Providers' staff and every account (admins) -----------------------------------------------

ProviderManager = Annotated[Caller, Depends(platform_context(Permission.PROVIDERS_MANAGE))]
UserAdmin = Annotated[Caller, Depends(platform_context(Permission.USERS_ADMINISTER))]
UserDeleter = Annotated[Caller, Depends(platform_context(Permission.USERS_DELETE))]


@router.post("/admin/providers/{provider_id}/staff", name="providers.add_staff", status_code=201)
def add_staff_route(
    caller: ProviderManager, services: ServicesDep, provider_id: str, body: StaffIn
) -> InvitedOut:
    done = invite(
        caller.ctx,
        services.uow(),
        services.directory,
        services.tokens,
        services.links,
        Invite(body.email, body.name, ScopeKind.PROVIDER, provider_id, Role.PROVIDER_STAFF),
    )
    return InvitedOut(user=UserOut.of(done.user), new_account=done.new_account)


@router.delete("/admin/providers/{provider_id}/staff/{user_id}", name="providers.remove_staff")
def remove_staff_route(
    caller: ProviderManager, services: ServicesDep, provider_id: str, user_id: str
) -> UserOut:
    return UserOut.of(remove_staff(caller.ctx, services.uow(), provider_id, user_id))


@router.get("/admin/users", name="users.list")
def users_list_route(
    caller: UserAdmin,
    services: ServicesDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    include_deleted: bool = False,
) -> UserPageOut:
    """Every user (not purged ones), by name; `q` matches the name or the email."""
    users = list_users(
        caller.ctx, services.uow(immediate=False), query=q, include_deleted=include_deleted
    )
    return UserPageOut(items=[UserOut.of(u) for u in users], total=len(users))


@router.post("/admin/users/{user_id}/lock", name="users.lock")
def lock_route(caller: UserAdmin, services: ServicesDep, user_id: str) -> UserOut:
    """Locks the account and ends its sessions."""
    return UserOut.of(lock_user(caller.ctx, services.uow(), user_id))


@router.post("/admin/users/{user_id}/unlock", name="users.unlock")
def unlock_route(caller: UserAdmin, services: ServicesDep, user_id: str) -> UserOut:
    return UserOut.of(unlock_user(caller.ctx, services.uow(), user_id))


@router.post("/admin/users/{user_id}/logout", name="users.force_logout", status_code=204)
def force_logout_route(caller: UserAdmin, services: ServicesDep, user_id: str) -> None:
    force_logout(caller.ctx, services.uow(), user_id)


@router.post("/admin/users/{user_id}/delete", name="users.delete")
def delete_user_route(caller: UserDeleter, services: ServicesDep, user_id: str) -> UserOut:
    """Soft delete: the account cannot log in and can be restored."""
    return UserOut.of(delete_user(caller.ctx, services.uow(), user_id))


@router.post("/admin/users/{user_id}/restore", name="users.restore")
def restore_user_route(caller: UserDeleter, services: ServicesDep, user_id: str) -> UserOut:
    return UserOut.of(restore_user(caller.ctx, services.uow(), user_id))


@router.post("/admin/users/{user_id}/purge", name="users.purge")
def purge_user_route(caller: UserDeleter, services: ServicesDep, user_id: str) -> UserOut:
    """Anonymises a deleted account for good."""
    return UserOut.of(purge_user(caller.ctx, services.uow(), user_id))
