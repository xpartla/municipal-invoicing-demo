"""Ports of the tenancy context: what it needs from identity about logins (the composition
root's adapter works on the same session, so a command spanning both commits once)."""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LoginRef:
    """A user's membership in a customer or a provider, as the user screens list it."""

    user_id: str
    name: str
    email: str | None
    role: str
    active: bool
    """Whether the membership is active (plan §2 decision 49)."""
    status: str
    """The account's status: invited, active, deleted."""
    locked: bool


class Logins(Protocol):
    def of_customers(self, customer_ids: Collection[str]) -> dict[str, list[LoginRef]]:
        """The logins of each customer, by name; deleted and purged accounts left out."""
        ...

    def staff_of(self, provider_ids: Collection[str]) -> dict[str, list[LoginRef]]:
        """The active staff of each provider, by name."""
        ...

    def deactivate_staff(self, provider_id: str) -> int:
        """Deactivates every staff membership of the provider; returns how many."""
        ...

    def remove_customer_memberships(self, customer_id: str) -> int:
        """Removes every membership in the customer (a purge); returns how many."""
        ...
