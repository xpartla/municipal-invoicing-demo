"""Access policies for application tests."""

from dataclasses import dataclass, field


@dataclass
class Grants:
    """Allows exactly the granted permissions: `customer` ones in the named customers,
    `provider` ones in the named providers, `platform` ones with neither."""

    customer: set[tuple[str, str]] = field(default_factory=set)
    provider: set[tuple[str, str]] = field(default_factory=set)
    platform: set[str] = field(default_factory=set)
    asked: list[tuple[str, str | None, str | None]] = field(default_factory=list)

    def allows(self, permission: str, customer_id: str | None, provider_id: str | None) -> bool:
        self.asked.append((permission, customer_id, provider_id))
        if customer_id is not None:
            return (permission, customer_id) in self.customer
        if provider_id is not None:
            return (permission, provider_id) in self.provider
        return permission in self.platform
