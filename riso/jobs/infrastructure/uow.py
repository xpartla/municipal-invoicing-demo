"""The jobs unit of work on SQLAlchemy."""

from collections.abc import Callable

from riso.jobs.application.queue import RepositoryJobQueue
from riso.jobs.application.registry import JobRegistry
from riso.jobs.infrastructure.repository import SqlJobRepository
from riso.platform.db import Database
from riso.platform.uow import SqlUnitOfWork
from riso.shared.clock import Clock
from riso.shared.ids import IdGenerator


class SqlJobsUnitOfWork(SqlUnitOfWork):
    jobs: SqlJobRepository
    queue: RepositoryJobQueue

    def __init__(
        self,
        db: Database,
        registry: JobRegistry,
        *,
        clock: Clock,
        ids: IdGenerator,
        immediate: bool = True,
    ) -> None:
        super().__init__(db, clock=clock, ids=ids, immediate=immediate)
        self._registry = registry

    def _start(self) -> None:
        self.jobs = SqlJobRepository(self.session)
        self.queue = RepositoryJobQueue(self.jobs, self._registry, self.clock, self.ids)


def jobs_uow_factory(
    db: Database, registry: JobRegistry, *, clock: Clock, ids: IdGenerator
) -> Callable[[bool], SqlJobsUnitOfWork]:
    """What the worker needs: a unit of work, with BEGIN IMMEDIATE unless told otherwise."""

    def make(immediate: bool) -> SqlJobsUnitOfWork:
        return SqlJobsUnitOfWork(db, registry, clock=clock, ids=ids, immediate=immediate)

    return make
