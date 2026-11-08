"""Request dependencies: the services, the CSRF check, the session and the caller's context
(guide §6.5, plan §4.4, §5.3).

Two kinds of dependency resolve the services. The access dependencies (`self_context`,
`customer_context`, …) use `_services` internally; route handlers take theirs from
`get_services`, declared after their access dependency. The permission-matrix test
overrides `get_services` to stop a request once access was granted, before the handler
runs, so it can call every route without side effects.

Cookies (plan §5.3):

- `riso_session`: the session token. HttpOnly, SameSite=Lax, Secure when configured.
- `riso_csrf`: the CSRF token, readable by the page, which sends it back in the
  `X-CSRF-Token` header on every unsafe request. Before a login it is a random value set by
  `CsrfCookieMiddleware` (a plain double submit); with a session it is the session's own
  token, and the header must match the session's copy.
"""

import secrets
from dataclasses import dataclass, replace
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, Response

from riso.api.composition import Services
from riso.api.middleware import CSRF_COOKIE_NAME
from riso.api.permissions_matrix import Scope
from riso.identity.application.access import MembershipPolicy
from riso.identity.application.auth import Authenticated, authenticate
from riso.identity.domain import ABSOLUTE_LIMIT, Permission
from riso.shared.context import RequestContext
from riso.shared.errors import NotFound, PermissionDenied, Unauthenticated

SESSION_COOKIE = "riso_session"
CSRF_COOKIE = CSRF_COOKIE_NAME
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _services(request: Request) -> Services:
    services = getattr(request.app.state, "services", None)
    if services is None:
        raise HTTPException(503, "this app runs without a database")
    return cast(Services, services)


def get_services(request: Request) -> Services:
    """The services, for route handlers (see the module docstring)."""
    return _services(request)


ServicesDep = Annotated[Services, Depends(get_services)]


def check_csrf(request: Request) -> None:
    """Every unsafe request carries the `riso_csrf` cookie's value in the header. With a
    session, `_caller` also compares it with the session's token."""
    if request.method not in UNSAFE_METHODS:
        return
    header = request.headers.get(CSRF_HEADER, "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    if not header or not cookie or not secrets.compare_digest(header, cookie):
        raise PermissionDenied("CSRF token missing or wrong")


@dataclass(frozen=True, slots=True)
class Caller:
    """Who calls: the session (None for an anonymous caller), the access policy and the
    request context the use cases receive."""

    auth: Authenticated | None
    policy: MembershipPolicy | None
    ctx: RequestContext

    def required(self) -> Authenticated:
        if self.auth is None:
            raise Unauthenticated("not logged in")
        return self.auth


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or "-")


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _caller(request: Request, services: Annotated[Services, Depends(_services)]) -> Caller:
    token = request.cookies.get(SESSION_COOKIE)
    anonymous = RequestContext(_request_id(request), None, ip=_ip(request))
    auth = authenticate(services.uow, token, anonymous) if token else None
    if auth is None:
        return Caller(None, None, anonymous)
    if request.method in UNSAFE_METHODS:
        header = request.headers.get(CSRF_HEADER, "")
        if not secrets.compare_digest(header, auth.csrf_token):
            raise PermissionDenied("CSRF token does not match the session")
    policy = services.policy(auth.grants)
    ctx = RequestContext(
        request_id=_request_id(request),
        actor_id=auth.actor_id,
        real_actor_id=auth.real_actor_id,
        ip=_ip(request),
        policy=policy,
    )
    return Caller(auth, policy, ctx)


# Access dependencies ----------------------------------------------------------------------
#
# Each route declares exactly one of these, first among its parameters. They are callable
# instances carrying their scope and permission, so the permission-matrix test can check that
# a route enforces what its entry in `permissions_matrix.MATRIX` says.


@dataclass(frozen=True, slots=True)
class PublicAccess:
    """Anyone, logged in or not."""

    scope: Scope = Scope.PUBLIC
    permission: Permission | None = None
    personal: bool = False

    def __call__(self, caller: Annotated[Caller, Depends(_caller)]) -> Caller:
        return caller


@dataclass(frozen=True, slots=True)
class SelfAccess:
    """The caller's own account: any logged-in user (401 otherwise). With `personal`, the
    route changes a credential and refuses an impersonating admin (403, plan §5.4)."""

    personal: bool = False
    scope: Scope = Scope.SELF
    permission: Permission | None = None

    def __call__(self, caller: Annotated[Caller, Depends(_caller)]) -> Caller:
        caller.required()
        if self.personal and caller.ctx.impersonating:
            raise PermissionDenied("not while impersonating")
        return caller


@dataclass(frozen=True, slots=True)
class CustomerAccess:
    """`/api/customers/{customer_id}/…`: the customer must be reachable (404 otherwise, so its
    existence does not leak), and the permission held in it (403 otherwise). The request
    context gets the acting customer."""

    permission: Permission
    scope: Scope = Scope.CUSTOMER
    personal: bool = False

    def __call__(self, customer_id: str, caller: Annotated[Caller, Depends(_caller)]) -> Caller:
        auth = caller.required()
        assert caller.policy is not None
        if not caller.policy.can_access_customer(customer_id):
            raise NotFound(f"no customer {customer_id}")
        ctx = replace(caller.ctx, customer_id=customer_id)
        ctx.require(self.permission, customer_id)
        return Caller(auth, caller.policy, ctx)


@dataclass(frozen=True, slots=True)
class ProviderAccess:
    """`/api/providers/{provider_id}/…`: the caller is staff of the provider, or an admin
    (404 otherwise), and holds the permission there (403 otherwise)."""

    permission: Permission
    scope: Scope = Scope.PROVIDER
    personal: bool = False

    def __call__(self, provider_id: str, caller: Annotated[Caller, Depends(_caller)]) -> Caller:
        caller.required()
        policy = caller.policy
        assert policy is not None
        if not policy.is_admin and provider_id not in policy.provider_ids:
            raise NotFound(f"no provider {provider_id}")
        caller.ctx.require(self.permission, provider_id=provider_id)
        return caller


@dataclass(frozen=True, slots=True)
class PlatformAccess:
    """Platform routes (`/api/admin/…`): a logged-in caller holding the permission on the
    platform, which only admins do; 401 or 403 otherwise."""

    permission: Permission
    scope: Scope = Scope.PLATFORM
    personal: bool = False

    def __call__(self, caller: Annotated[Caller, Depends(_caller)]) -> Caller:
        caller.required()
        caller.ctx.require(self.permission)
        return caller


Access = PublicAccess | SelfAccess | CustomerAccess | ProviderAccess | PlatformAccess
ACCESS_TYPES = (PublicAccess, SelfAccess, CustomerAccess, ProviderAccess, PlatformAccess)


def public_context() -> PublicAccess:
    return PublicAccess()


def self_context(*, personal: bool = False) -> SelfAccess:
    return SelfAccess(personal)


def customer_context(permission: Permission) -> CustomerAccess:
    return CustomerAccess(permission)


def provider_context(permission: Permission) -> ProviderAccess:
    return ProviderAccess(permission)


def platform_context(permission: Permission) -> PlatformAccess:
    return PlatformAccess(permission)


AnyCaller = Annotated[Caller, Depends(PublicAccess())]
SelfCaller = Annotated[Caller, Depends(SelfAccess())]
PersonalCaller = Annotated[Caller, Depends(SelfAccess(personal=True))]


# Cookies ----------------------------------------------------------------------------------


def set_session_cookies(
    response: Response, services: Services, token: str, csrf_token: str
) -> None:
    secure = services.settings.cookie_secure
    max_age = int(ABSOLUTE_LIMIT.total_seconds())
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        path="/",
        httponly=True,
        samesite="lax",
        secure=secure,
    )
    set_csrf_cookie(response, csrf_token, secure=secure)


def clear_session_cookies(response: Response, services: Services) -> None:
    secure = services.settings.cookie_secure
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=secure)
    set_csrf_cookie(response, services.tokens.new_token(), secure=secure)


def set_csrf_cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(CSRF_COOKIE, token, path="/", samesite="lax", secure=secure)
