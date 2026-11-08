"""The repository protocol of the codelists context.

A list's owner is a customer or, for a global list, nobody: every method takes the
`customer_id`, None for the global lists, so no query reads a customer's lists without it
(guide §6.4).
"""

from typing import Protocol

from riso.codelists.domain.conventions import CustomerConventions
from riso.codelists.domain.kinds import ListKind
from riso.codelists.domain.version import CodeListVersion, VersionInfo


class CodeListRepository(Protocol):
    def add(self, version: CodeListVersion) -> None:
        """Stores a new version with its entries."""
        ...

    def save(self, version: CodeListVersion) -> None:
        """Stores a version's status, the only thing that changes after it is added."""
        ...

    def get(self, customer_id: str | None, version_id: str) -> CodeListVersion:
        """Raises `NotFound` when there is no such version of the owner's."""
        ...

    def active(
        self, customer_id: str | None, kind: ListKind, year: int
    ) -> CodeListVersion | None: ...

    def active_ids(self, customer_id: str | None, year: int) -> dict[ListKind, str]:
        """The active version of each of the owner's kinds for the year."""
        ...

    def history(self, customer_id: str | None, kind: ListKind, year: int) -> list[VersionInfo]:
        """Every version of the list for the year, the newest first."""
        ...

    def years(self, customer_id: str | None) -> list[int]:
        """The years the owner has any list for."""
        ...


class ConventionsRepository(Protocol):
    def get(self, customer_id: str, year: int) -> CustomerConventions | None: ...

    def save(self, conventions: CustomerConventions) -> None:
        """Adds or replaces the customer's conventions for the year."""
        ...

    def years(self, customer_id: str) -> list[int]: ...
