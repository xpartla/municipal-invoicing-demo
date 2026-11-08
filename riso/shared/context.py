"""The request context every use case receives (plan §4.4).

It says who acts (the principal), who really acts when an admin impersonates someone, which
customer the request works in, and the request ID for the logs. `require()` asks the access
policy whether a permission holds, and raises `PermissionDenied` when it does not.

This is the skeleton from P2-M0. P2-M1 fills in the policy from memberships and roles; the
permissions themselves are an enum in `riso.identity.domain` (a `StrEnum`, so a plain string
works here too).
"""

from dataclasses import dataclass, field
from typing import Protocol

from riso.shared.errors import PermissionDenied


class AccessPolicy(Protocol):
    def allows(self, permission: str, customer_id: str | None) -> bool:
        """Whether the principal holds `permission`, in `customer_id` when it is given."""
        ...


class DenyAll:
    """The policy of an anonymous request."""

    def allows(self, permission: str, customer_id: str | None) -> bool:
        return False


class AllowAll:
    """The policy of trusted internal callers: the CLI and tests."""

    def allows(self, permission: str, customer_id: str | None) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str
    actor_id: str | None
    """The principal: the user the request acts as. None for an anonymous request."""
    real_actor_id: str | None = None
    """The admin behind an impersonation; None otherwise."""
    customer_id: str | None = None
    """The acting customer, from the URL; None outside customer routes."""
    policy: AccessPolicy = field(default_factory=DenyAll)

    @property
    def impersonating(self) -> bool:
        return self.real_actor_id is not None

    def allows(self, permission: str, customer_id: str | None = None) -> bool:
        return self.policy.allows(permission, customer_id)

    def require(self, permission: str, customer_id: str | None = None) -> None:
        """Raises `PermissionDenied` unless the principal holds the permission. Use cases call
        this first, even when the route already checked, because jobs and the CLI call them
        too."""
        if not self.policy.allows(permission, customer_id):
            where = f" in customer {customer_id}" if customer_id else ""
            raise PermissionDenied(f"{permission} denied{where}")

    @classmethod
    def anonymous(cls, request_id: str) -> "RequestContext":
        return cls(request_id=request_id, actor_id=None)

    @classmethod
    def system(cls, request_id: str, actor_id: str | None = None) -> "RequestContext":
        """A trusted internal caller (the CLI, seeding), allowed everything."""
        return cls(request_id=request_id, actor_id=actor_id, policy=AllowAll())
