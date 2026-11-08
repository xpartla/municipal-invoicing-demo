"""An audit event: one entry of the append-only audit log (plan §4.7, §11, §12)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: str
    at: datetime
    action: str
    """`<area>.<what>`, e.g. `auth.login`, `customer.contact_updated`, `impersonation.started`."""
    actor_id: str | None
    """Whom the request acted as; None for an anonymous request (a failed login)."""
    real_actor_id: str | None = None
    """The admin behind an impersonation."""
    customer_id: str | None = None
    """The acting customer, for customer-scoped actions."""
    target_type: str | None = None
    target_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    ip: str | None = None


@dataclass(frozen=True, slots=True)
class AuditFilter:
    actor_id: str | None = None
    """Matches the actor or the real actor."""
    customer_id: str | None = None
    action: str | None = None
    """A whole action, or a prefix ending in a dot (`auth.`)."""
    since: datetime | None = None
    until: datetime | None = None
