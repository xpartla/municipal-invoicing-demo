"""The identity API: logging in and out, and the caller's own account (`/api/auth/…`,
`/api/me/…`)."""

from fastapi import APIRouter, Depends, Request, Response

from riso.api.deps import (
    AnyCaller,
    SelfCaller,
    ServicesDep,
    check_csrf,
    clear_session_cookies,
    set_session_cookies,
)
from riso.identity.api.models import LoginIn, MeOut, SessionOut
from riso.identity.application.auth import (
    Login,
    authenticate,
    list_sessions,
    login,
    logout,
    logout_everywhere,
    me,
)
from riso.shared.errors import Unauthenticated

router = APIRouter(prefix="/api", dependencies=[Depends(check_csrf)], tags=["identity"])


@router.post("/auth/login", name="auth.login")
def login_route(
    body: LoginIn, request: Request, response: Response, caller: AnyCaller, services: ServicesDep
) -> MeOut:
    """Logs in with the login email and password. Sets the session and CSRF cookies. Answers
    401 for any failure and 429 (with `Retry-After`) while throttled."""
    done = login(
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
    auth = authenticate(services.uow, done.token)
    if auth is None:  # pragma: no cover - the session was made a moment ago
        raise Unauthenticated("login failed")
    return MeOut.of(me(auth, services.policy(auth.grants), services.directory))


@router.post("/auth/logout", name="auth.logout", status_code=204)
def logout_route(response: Response, caller: SelfCaller, services: ServicesDep) -> None:
    """Ends this session."""
    logout(services.uow(), caller.required().session_id)
    clear_session_cookies(response, services)


@router.post("/auth/logout-all", name="auth.logout_all", status_code=204)
def logout_all_route(response: Response, caller: SelfCaller, services: ServicesDep) -> None:
    """Ends every session of the caller, this one included."""
    logout_everywhere(services.uow(), caller.required().actor_id)
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
