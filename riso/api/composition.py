"""The composition root: it builds the database, the registries, the units of work and the
worker from the settings. It is the one place outside a context that may import the
context's infrastructure (the import-linter contracts allow `riso.api`); the CLI and the app
factory get their services from here."""

import os
import socket
from dataclasses import dataclass, field

from riso.jobs import JobRegistry, Worker, register_builtin
from riso.jobs.infrastructure.thread import WorkerThread
from riso.jobs.infrastructure.uow import SqlJobsUnitOfWork, jobs_uow_factory
from riso.platform.db import Database
from riso.platform.settings import Settings
from riso.platform.storage import LocalFileStorage
from riso.shared.clock import Clock, SystemClock
from riso.shared.ids import IdGenerator, UuidV7Generator


def build_registry() -> JobRegistry:
    """Every job kind. Contexts add theirs here as they get them."""
    return register_builtin(JobRegistry())


@dataclass
class Services:
    settings: Settings
    db: Database
    clock: Clock
    ids: IdGenerator
    registry: JobRegistry
    storage: LocalFileStorage
    _threads: list[WorkerThread] = field(default_factory=list)

    def jobs_uow(self, immediate: bool = True) -> SqlJobsUnitOfWork:
        return SqlJobsUnitOfWork(
            self.db, self.registry, clock=self.clock, ids=self.ids, immediate=immediate
        )

    def worker(self, worker_id: str | None = None) -> Worker:
        return Worker(
            jobs_uow_factory(self.db, self.registry, clock=self.clock, ids=self.ids),
            self.registry,
            worker_id=worker_id or f"{socket.gethostname()}-{os.getpid()}",
        )

    def worker_thread(self, poll_interval: float = 1.0) -> WorkerThread:
        thread = WorkerThread(self.worker(), poll_interval=poll_interval)
        self._threads.append(thread)
        return thread

    def close(self) -> None:
        for thread in self._threads:
            thread.stop()
        self.db.dispose()


def build_services(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    registry: JobRegistry | None = None,
) -> Services:
    settings = settings or Settings()
    clock = clock or SystemClock()
    return Services(
        settings=settings,
        db=Database(settings.db_url),
        clock=clock,
        ids=UuidV7Generator(clock),
        registry=registry or build_registry(),
        storage=LocalFileStorage(settings.files_dir, clock),
    )
