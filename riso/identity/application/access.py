"""The access policy (plan §4.4, §5.2): who may do what, where.

A principal reaches a customer through

- an active membership in it (its role's permissions apply there);
- an active `provider_staff` membership in the provider the customer is assigned to;
- the platform admin role (every customer, deleted ones included).

A deleted customer is reachable by admins only. Provider permissions apply in the staff
member's own provider; platform permissions are the admin's. The policy asks the tenancy
directory about customers once per customer and request.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from riso.identity.application.ports import CustomerRef, TenancyDirectory
from riso.identity.domain import ROLE_PERMISSIONS, Permission, Role, ScopeKind

ALL = frozenset(Permission)


@dataclass(frozen=True, slots=True)
class Grant:
    """An active membership."""

    kind: ScopeKind
    scope_id: str | None
    role: Role


class MembershipPolicy:
    def __init__(self, grants: Iterable[Grant], directory: TenancyDirectory) -> None:
        self._directory = directory
        self._admin = False
        self._customers: dict[str, frozenset[Permission]] = {}
        self._providers: dict[str, frozenset[Permission]] = {}
        for grant in grants:
            permissions = ROLE_PERMISSIONS[grant.role]
            if grant.kind is ScopeKind.PLATFORM:
                self._admin = True
            elif grant.kind is ScopeKind.CUSTOMER and grant.scope_id:
                self._customers[grant.scope_id] = permissions
            elif grant.kind is ScopeKind.PROVIDER and grant.scope_id:
                self._providers[grant.scope_id] = permissions
        self._seen: dict[str, CustomerRef | None] = {}

    @property
    def is_admin(self) -> bool:
        return self._admin

    @property
    def provider_ids(self) -> list[str]:
        return list(self._providers)

    @property
    def customer_ids(self) -> list[str]:
        """The customers of the principal's own customer memberships."""
        return list(self._customers)

    def _customer(self, customer_id: str) -> CustomerRef | None:
        if customer_id not in self._seen:
            self._seen[customer_id] = self._directory.customer(customer_id)
        return self._seen[customer_id]

    def can_access_customer(self, customer_id: str) -> bool:
        customer = self._customer(customer_id)
        if customer is None:
            return False
        if self._admin:
            return True
        if not customer.active:
            return False
        return customer_id in self._customers or (
            customer.provider_id is not None and customer.provider_id in self._providers
        )

    def in_customer(self, customer_id: str) -> frozenset[Permission]:
        if not self.can_access_customer(customer_id):
            return frozenset()
        if self._admin:
            return ALL
        customer = self._customer(customer_id)
        held: set[Permission] = set(self._customers.get(customer_id, ()))
        if customer is not None and customer.provider_id in self._providers:
            held |= self._providers[customer.provider_id]
        return frozenset(held)

    def in_provider(self, provider_id: str) -> frozenset[Permission]:
        if self._admin:
            return ALL
        return self._providers.get(provider_id, frozenset())

    def on_platform(self) -> frozenset[Permission]:
        return ALL if self._admin else frozenset()

    def allows(self, permission: str, customer_id: str | None, provider_id: str | None) -> bool:
        if customer_id is not None:
            return permission in self.in_customer(customer_id)
        if provider_id is not None:
            return permission in self.in_provider(provider_id)
        return permission in self.on_platform()

    def accessible_customers(self) -> list[CustomerRef]:
        """The active customers the principal can open, by name."""
        if self._admin:
            return self._directory.customers()
        found = {
            c.id: c
            for c in self._directory.customers(ids=list(self._customers))
            + self._directory.customers(provider_ids=list(self._providers))
        }
        return sorted(found.values(), key=lambda c: (c.name, c.id))
