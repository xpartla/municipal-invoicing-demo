"""The composition root: it builds the database, the registries, the units of work and the
worker from the settings. It is the one place outside a context that may import the
context's infrastructure (the import-linter contracts allow `riso.api`); the CLI and the app
factory get their services from here."""

import os
import socket
from dataclasses import dataclass, field

from riso.api.adapters import SpaLinks, SqlTenancyDirectory
from riso.api.uow import AppUnitOfWork
from riso.identity.application.access import Grant, MembershipPolicy
from riso.identity.domain import PasswordHasher, PasswordPolicy
from riso.identity.infrastructure.hashing import Argon2Hasher, default_policy
from riso.identity.infrastructure.sessions import SecretsTokenGenerator
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
    hasher: PasswordHasher
    password_policy: PasswordPolicy
    tokens: SecretsTokenGenerator
    directory: SqlTenancyDirectory
    links: SpaLinks
    _threads: list[WorkerThread] = field(default_factory=list)

    def uow(self, immediate: bool = True) -> AppUnitOfWork:
        """A unit of work over every context; with BEGIN IMMEDIATE unless told otherwise."""
        return AppUnitOfWork(self.db, clock=self.clock, ids=self.ids, immediate=immediate)

    def policy(self, grants: tuple[Grant, ...]) -> MembershipPolicy:
        return MembershipPolicy(grants, self.directory)

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
    hasher: PasswordHasher | None = None,
) -> Services:
    settings = settings or Settings()
    clock = clock or SystemClock()
    db = Database(settings.db_url)
    return Services(
        settings=settings,
        db=db,
        clock=clock,
        ids=UuidV7Generator(clock),
        registry=registry or build_registry(),
        storage=LocalFileStorage(settings.files_dir, clock),
        hasher=hasher or Argon2Hasher(),
        password_policy=default_policy(),
        tokens=SecretsTokenGenerator(),
        directory=SqlTenancyDirectory(db),
        links=SpaLinks(settings.public_url),
    )
