"""The in-memory code list repository and the codelists unit of work."""

from riso.codelists.domain import CodeListVersion, ListKind, VersionInfo, VersionStatus
from riso.shared import NotFound
from tests.fakes.memory import SnapshotStore, StoresUnitOfWork
from tests.fakes.ports import RecordingAudit
from tests.fakes.uow import InMemoryUnitOfWork


class InMemoryCodeLists(SnapshotStore):
    def __init__(self, uow: InMemoryUnitOfWork) -> None:
        super().__init__()
        self._uow = uow

    def _tracked(self, version: CodeListVersion) -> CodeListVersion:
        self._uow.track(version)
        return version

    def add(self, version: CodeListVersion) -> None:
        self.put(version.id, version)
        self._uow.track(version)

    def save(self, version: CodeListVersion) -> None:
        stored = self.rows.get(version.id)
        if stored is None or stored.customer_id != version.customer_id:
            raise NotFound(f"no code list version {version.id}")
        stored.status = version.status  # the stored copy is private to the store

    def get(self, customer_id: str | None, version_id: str) -> CodeListVersion:
        stored = self.rows.get(version_id)
        if stored is None or stored.customer_id != customer_id:
            raise NotFound(f"no code list version {version_id}")
        return self._tracked(self.take(version_id))

    def _of(self, customer_id: str | None, year: int) -> list[CodeListVersion]:
        return [v for v in self.rows.values() if v.customer_id == customer_id and v.year == year]

    def active(self, customer_id: str | None, kind: ListKind, year: int) -> CodeListVersion | None:
        for version in self._of(customer_id, year):
            if version.kind is kind and version.status is VersionStatus.ACTIVE:
                return self._tracked(self.take(version.id))
        return None

    def active_ids(self, customer_id: str | None, year: int) -> dict[ListKind, str]:
        return {
            v.kind: v.id for v in self._of(customer_id, year) if v.status is VersionStatus.ACTIVE
        }

    def history(self, customer_id: str | None, kind: ListKind, year: int) -> list[VersionInfo]:
        found = [v.info() for v in self._of(customer_id, year) if v.kind is kind]
        return sorted(found, key=lambda info: -info.number)

    def years(self, customer_id: str | None) -> list[int]:
        return sorted({v.year for v in self.rows.values() if v.customer_id == customer_id})

    def remove_customer(self, customer_id: str) -> None:
        """What the database's cascade does when the customer is purged."""
        for key in [k for k, v in self.rows.items() if v.customer_id == customer_id]:
            del self.rows[key]


class InMemoryCodelistsUnitOfWork(StoresUnitOfWork):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.audit = self.store(RecordingAudit())
        self.codelists = self.store(InMemoryCodeLists(self))
        self.conventions = self.store(InMemoryConventions())


class InMemoryConventions(SnapshotStore):
    def get(self, customer_id: str, year: int):
        return self.take((customer_id, year)) if (customer_id, year) in self.rows else None

    def save(self, conventions) -> None:
        self.put((conventions.customer_id, conventions.year), conventions)

    def years(self, customer_id: str) -> list[int]:
        return sorted(year for (cid, year) in self.rows if cid == customer_id)
