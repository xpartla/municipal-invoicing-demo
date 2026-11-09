"""A customer's coding conventions for one year (plan §6.4, §2 decision 56): one document per
customer and year, edited in place. Each change raises the revision by one, so an editor
can tell that someone else saved in between, and an invoice can record the revision it was
coded with (P2-M4). The audit keeps every document's before and after.
"""

from dataclasses import dataclass, field
from datetime import datetime

from riso.knowledge import Conventions
from riso.shared.errors import Conflict
from riso.shared.events import DomainEvent


@dataclass(frozen=True, slots=True)
class ConventionsChanged(DomainEvent):
    customer_id: str
    year: int
    revision: int


@dataclass(slots=True)
class CustomerConventions:
    customer_id: str
    year: int
    revision: int
    document: Conventions
    updated_at: datetime
    updated_by: str | None
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        customer_id: str,
        year: int,
        document: Conventions,
        at: datetime,
        actor: str | None,
    ) -> "CustomerConventions":
        conventions = cls(customer_id, year, 1, document, at, actor)
        conventions.events.append(ConventionsChanged(customer_id, year, 1))
        return conventions

    def replace(
        self,
        document: Conventions,
        at: datetime,
        actor: str | None,
        *,
        expected_revision: int | None = None,
    ) -> bool:
        """Takes the new document; False (and no new revision) when it equals the current
        one. `expected_revision` is the revision the editor started from."""
        if expected_revision is not None and expected_revision != self.revision:
            raise Conflict(
                f"conventions {self.year} are at revision {self.revision}, "
                f"not {expected_revision}; reload them"
            )
        if document == self.document:
            return False
        self.document = document
        self.revision += 1
        self.updated_at = at
        self.updated_by = actor
        self.events.append(ConventionsChanged(self.customer_id, self.year, self.revision))
        return True
