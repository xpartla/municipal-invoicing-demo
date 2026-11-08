"""Who may call each API route (guide §6.5).

Every route under `/api` has a unique `name` and an entry here: the permission it needs and
the scope the permission is checked in. `tests/api/test_permissions.py` fails for a route
without an entry, and for an entry without a route. From P2-M1 the same test generates the
role × route × own/foreign customer matrix from this table.

The demo's routes are `public` until P2-M4 replaces them: the demo has no logins.
"""

from dataclasses import dataclass
from enum import StrEnum

from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts

from riso.identity.domain import Permission


class Scope(StrEnum):
    PUBLIC = "public"
    """Anyone, logged in or not."""
    SELF = "self"
    """The caller's own account (`/api/me/…`, `/api/auth/…`)."""
    CUSTOMER = "customer"
    """A customer the caller can access (`/api/customers/{customer_id}/…`)."""
    PROVIDER = "provider"
    """A service provider the caller belongs to (`/api/providers/{provider_id}/…`)."""
    PLATFORM = "platform"
    """Platform administration (`/api/admin/…`)."""


@dataclass(frozen=True, slots=True)
class RouteAccess:
    scope: Scope
    permission: str | None = None
    """The permission checked in the scope; None only for public and self routes."""


def public() -> RouteAccess:
    return RouteAccess(Scope.PUBLIC)


def own() -> RouteAccess:
    return RouteAccess(Scope.SELF)


MATRIX: dict[str, RouteAccess] = {
    # Identity: logging in and out, the caller's own account.
    "auth.login": public(),
    "auth.logout": own(),
    "auth.logout_all": own(),
    "me.get": own(),
    "me.sessions": own(),
    "me.change_password": own(),
    "me.request_email_change": own(),
    "auth.token_info": public(),
    "auth.accept_invitation": public(),
    "auth.request_reset": public(),
    "auth.reset_password": public(),
    "auth.confirm_email_change": public(),
    # Platform tools.
    "outbox.list": RouteAccess(Scope.PLATFORM, Permission.OUTBOX_READ),
    "outbox.get": RouteAccess(Scope.PLATFORM, Permission.OUTBOX_READ),
    # The demo (P2-M4 replaces these).
    "legacy.entities": public(),
    "legacy.reference": public(),
    "legacy.invoices": public(),
    "legacy.invoice": public(),
    "legacy.code": public(),
    "legacy.line": public(),
    "legacy.feedback": public(),
    "legacy.feedback_log": public(),
    "legacy.counters": public(),
    "legacy.eval": public(),
}


@dataclass(frozen=True, slots=True)
class ApiRoute:
    """A route under `/api`, as the app serves it (included routers flattened)."""

    name: str
    path: str
    methods: frozenset[str]
    route: APIRoute


def api_routes(app: FastAPI) -> list[ApiRoute]:
    """Every `/api` route of the app. FastAPI 0.143 keeps included routers as their own
    entries in `app.routes`, so they are walked through `iter_route_contexts`."""
    found = []
    for context in iter_route_contexts(app.routes):
        route = context.original_route
        path = context.path or ""
        if isinstance(route, APIRoute) and path.startswith("/api"):
            found.append(ApiRoute(route.name, path, frozenset(route.methods or ()), route))
    return found
