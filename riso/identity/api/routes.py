"""The identity API: logging in and out, and the caller's own account (`/api/auth/…`,
`/api/me/…`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from riso.api.deps import (
    AnyCaller,
    Caller,
    PersonalCaller,
    SelfCaller,
    ServicesDep,
    check_csrf,
    clear_session_cookies,
    platform_context,
    set_session_cookies,
)
from riso.identity.api.models import (
    AcceptedOut,
    ChangePasswordIn,
    EmailChangeIn,
    ImpersonateIn,
    LoginIn,
    MeOut,
    ResetRequestIn,
    SessionOut,
    SetPasswordIn,
    TokenIn,
    TokenInfoOut,
)
from riso.identity.application.accounts import (
    accept_invitation,
    change_password,
    confirm_email_change,
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
from riso.identity.domain import Permission
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
