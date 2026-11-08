"""The `ServiceProvider` aggregate: a firm that keeps the books of several customers (plan §3,
§5.6). Its staff are users with the `provider_staff` role in it (identity's memberships).

Removing a provider keeps the row, so the audit and the history still name it; its staff
memberships are deactivated and its customers unassigned by the use case that removes it.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from riso.shared.errors import InvalidState
from riso.shared.events import DomainEvent
from riso.shared.values import Ico, clean_name


class ProviderStatus(StrEnum):
    ACTIVE = "active"
    REMOVED = "removed"


@dataclass(slots=True)
class ServiceProvider:
    id: str
    name: str
    created_at: datetime
    ico: Ico | None = None
    status: ProviderStatus = ProviderStatus.ACTIVE
    removed_at: datetime | None = None
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls, provider_id: str, name: str, at: datetime, *, ico: Ico | None = None
    ) -> "ServiceProvider":
        return cls(id=provider_id, name=clean_name(name), created_at=at, ico=ico)

    @property
    def active(self) -> bool:
        return self.status is ProviderStatus.ACTIVE

    def rename(self, name: str) -> None:
        if not self.active:
            raise InvalidState(f"provider {self.id} is removed")
        self.name = clean_name(name)

    def remove(self, at: datetime) -> None:
        if not self.active:
            raise InvalidState(f"provider {self.id} is already removed")
        self.status = ProviderStatus.REMOVED
        self.removed_at = at
