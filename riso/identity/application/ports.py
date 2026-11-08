"""Ports of the identity context: random tokens, and what it needs to know about customers and
providers (the tenancy context answers through an adapter the composition root wires)."""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Protocol


class TokenGenerator(Protocol):
    def new_token(self) -> str:
        """A new random, URL-safe token of 256 bits."""
        ...


@dataclass(frozen=True, slots=True)
class CustomerRef:
    id: str
    name: str
    ico: str
    provider_id: str | None
    active: bool


@dataclass(frozen=True, slots=True)
class ProviderRef:
    id: str
    name: str
    active: bool


class TenancyDirectory(Protocol):
    def customer(self, customer_id: str) -> CustomerRef | None:
        """The customer, deleted or not; None when there is no such customer."""
        ...

    def customers(
        self,
        *,
        ids: Collection[str] | None = None,
        provider_ids: Collection[str] | None = None,
    ) -> list[CustomerRef]:
        """Active customers by name: those with the IDs, or assigned to the providers, or
        (with neither) all of them."""
        ...

    def provider(self, provider_id: str) -> ProviderRef | None: ...

    def providers(self, ids: Collection[str]) -> list[ProviderRef]: ...


class Links(Protocol):
    """The SPA's addresses that mail links to. The token travels in the fragment, so it never
    reaches a server log."""

    def invitation(self, token: str) -> str: ...

    def password_reset(self, token: str) -> str: ...

    def email_change(self, token: str) -> str: ...

    def login(self) -> str: ...
