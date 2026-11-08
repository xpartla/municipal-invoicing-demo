"""Who may call each API route (guide §6.5).

Every route under `/api` has a unique `name` and an entry here: the permission it needs and
the scope the permission is checked in. `tests/api/test_permissions.py` fails for a route
without an entry, and for an entry without a route. From P2-M1 the same test generates the
role × route × own/foreign customer matrix from this table.

The demo's routes are `public` until P2-M4 replaces them: the demo has no logins.
"""

from dataclasses import dataclass
from enum import StrEnum


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


MATRIX: dict[str, RouteAccess] = {
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
