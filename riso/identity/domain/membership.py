"""Memberships: a user's role in a scope (plan §3, §5.1).

A scope is a customer, a service provider, or the platform. A user holds at most one role
per scope; the role must belong to the scope's kind (`ROLE_SCOPE`). Deactivating a
membership removes the access it gives without forgetting it (plan §2 decision 49), and
reactivating gives it back.
"""

from dataclasses import dataclass
from datetime import datetime

from riso.identity.domain.permissions import ROLE_SCOPE, Role, ScopeKind
from riso.shared.errors import InvalidState, ValidationFailed


@dataclass(frozen=True, slots=True)
class MembershipScope:
    kind: ScopeKind
    id: str | None
    """The customer or provider ID; None for the platform."""

    def __post_init__(self) -> None:
        if (self.kind is ScopeKind.PLATFORM) != (self.id is None):
            raise ValueError("the platform scope has no ID; the others need one")

    @classmethod
    def customer(cls, customer_id: str) -> "MembershipScope":
        return cls(ScopeKind.CUSTOMER, customer_id)

    @classmethod
    def provider(cls, provider_id: str) -> "MembershipScope":
        return cls(ScopeKind.PROVIDER, provider_id)

    @classmethod
    def platform(cls) -> "MembershipScope":
        return cls(ScopeKind.PLATFORM, None)


@dataclass(slots=True)
class Membership:
    id: str
    scope: MembershipScope
    role: Role
    created_at: datetime
    deactivated_at: datetime | None = None

    def __post_init__(self) -> None:
        if ROLE_SCOPE[self.role] is not self.scope.kind:
            raise ValidationFailed.on(
                "role", f"{self.role} is not held in a {self.scope.kind}", "role_scope"
            )

    @property
    def active(self) -> bool:
        return self.deactivated_at is None

    def deactivate(self, at: datetime) -> None:
        if not self.active:
            raise InvalidState(f"membership {self.id} is already inactive")
        self.deactivated_at = at

    def reactivate(self) -> None:
        if self.active:
            raise InvalidState(f"membership {self.id} is already active")
        self.deactivated_at = None
