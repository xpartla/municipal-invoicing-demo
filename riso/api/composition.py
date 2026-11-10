"""The composition root: it builds the database, the registries, the units of work and the
worker from the settings. It is the one place outside a context that may import the
context's infrastructure (the import-linter contracts allow `riso.api`); the CLI and the app
factory get their services from here."""

import os
import socket
from dataclasses import dataclass, field

from riso.api.adapters import DbReferenceData, DbSupplierState, SpaLinks, SqlTenancyDirectory
from riso.api.uow import AppUnitOfWork
from riso.exchange.application.copy import COPY_JOB, CopyJobs
from riso.exchange.application.exports import EXPORT_JOB, ExportJobs
from riso.exchange.application.imports import ImportJobs
from riso.exchange.infrastructure.readers import FileTableReader
from riso.exchange.infrastructure.writers import TableWriter
from riso.identity.application.access import Grant, MembershipPolicy
from riso.identity.application.ports import CustomerRef
from riso.identity.domain import PasswordHasher, PasswordPolicy
from riso.identity.infrastructure.hashing import Argon2Hasher, default_policy
from riso.identity.infrastructure.sessions import SecretsTokenGenerator
from riso.intake.application import EXTRACT_JOB, ExtractionJobs
from riso.intake.infrastructure.pages import FilePages
from riso.jobs import JobRegistry, Worker, register_builtin
from riso.jobs.domain import Job
from riso.jobs.infrastructure.thread import WorkerThread
from riso.jobs.infrastructure.uow import SqlJobsUnitOfWork, jobs_uow_factory
from riso.platform.db import Database
from riso.platform.settings import Settings
from riso.platform.storage import LocalFileStorage
from riso.shared.clock import Clock, SystemClock
from riso.shared.context import DenyAll, RequestContext
from riso.shared.errors import NotFound
from riso.shared.ids import IdGenerator, UuidV7Generator


def build_registry() -> JobRegistry:
    """The job kinds every installation has; `build_services` adds the contexts' kinds,
    whose handlers need the services."""
    return register_builtin(JobRegistry())


class CustomerDirectory:
    """The exchange context's `CustomerDirectory` port on the tenancy directory."""

    def __init__(self, directory: SqlTenancyDirectory) -> None:
        self._directory = directory

    def _customer(self, customer_id: str) -> CustomerRef:
        customer = self._directory.customer(customer_id)
        if customer is None:
            raise NotFound(f"no customer {customer_id}")
        return customer

    def ico_of(self, customer_id: str) -> str:
        return self._customer(customer_id).ico

    def provider_of(self, customer_id: str) -> str | None:
        return self._customer(customer_id).provider_id


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
    reader: FileTableReader = field(default_factory=FileTableReader)
    pages: FilePages = field(default_factory=FilePages)
    _threads: list[WorkerThread] = field(default_factory=list)

    def uow(self, immediate: bool = True) -> AppUnitOfWork:
        """A unit of work over every context; with BEGIN IMMEDIATE unless told otherwise."""
        return AppUnitOfWork(
            self.db, clock=self.clock, ids=self.ids, immediate=immediate, registry=self.registry
        )

    def reference_data(self) -> DbReferenceData:
        """The customer's settings, code lists and conventions, for the engine."""
        return DbReferenceData(lambda: self.uow(immediate=False))

    def supplier_state(self) -> DbSupplierState:
        """Supplier memory and counters from the database, for a coding outside a unit of
        work (the stateless coding route, the knowledge health report)."""
        return DbSupplierState(lambda: self.uow(immediate=False))

    def policy(self, grants: tuple[Grant, ...]) -> MembershipPolicy:
        return MembershipPolicy(grants, self.directory)

    def job_context(self, job: Job) -> RequestContext:
        """A job acts as the user who started it, with that user's current memberships (a
        user who can no longer log in has none). A job without a starter was queued by a
        trusted internal caller (the CLI, seeding) and is allowed everything."""
        request_id = f"job:{job.id}"
        if job.created_by is None:
            return RequestContext.system(request_id)
        with self.uow(immediate=False) as uow:
            try:
                user = uow.users.get(job.created_by)
            except NotFound:
                return RequestContext(request_id, job.created_by, policy=DenyAll())
            grants = (
                tuple(Grant(m.scope.kind, m.scope.id, m.role) for m in user.active_memberships())
                if user.can_log_in
                else ()
            )
        return RequestContext(
            request_id, job.created_by, customer_id=job.customer_id, policy=self.policy(grants)
        )

    def customers(self) -> CustomerDirectory:
        return CustomerDirectory(self.directory)

    def import_jobs(self) -> ImportJobs:
        return ImportJobs(self.uow, self.storage, self.reader, self.customers())

    def copy_jobs(self) -> CopyJobs:
        return CopyJobs(self.uow)

    def export_jobs(self) -> ExportJobs:
        return ExportJobs(self.uow, self.storage, TableWriter())

    def extraction_jobs(self) -> ExtractionJobs:
        return ExtractionJobs(self.uow)

    def jobs_uow(self, immediate: bool = True) -> SqlJobsUnitOfWork:
        return SqlJobsUnitOfWork(
            self.db, self.registry, clock=self.clock, ids=self.ids, immediate=immediate
        )

    def worker(self, worker_id: str | None = None) -> Worker:
        return Worker(
            jobs_uow_factory(self.db, self.registry, clock=self.clock, ids=self.ids),
            self.registry,
            worker_id=worker_id or f"{socket.gethostname()}-{os.getpid()}",
            context_factory=self.job_context,
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
    ids: IdGenerator | None = None,
    registry: JobRegistry | None = None,
    hasher: PasswordHasher | None = None,
) -> Services:
    settings = settings or Settings()
    clock = clock or SystemClock()
    db = Database(settings.db_url)
    services = Services(
        settings=settings,
        db=db,
        clock=clock,
        ids=ids or UuidV7Generator(clock),
        registry=registry or build_registry(),
        storage=LocalFileStorage(settings.files_dir, clock),
        hasher=hasher or Argon2Hasher(),
        password_policy=default_policy(),
        tokens=SecretsTokenGenerator(),
        directory=SqlTenancyDirectory(db),
        links=SpaLinks(settings.public_url),
    )
    if "import_dry_run" not in services.registry.names():
        services.import_jobs().register(services.registry)
    if COPY_JOB not in services.registry.names():
        services.copy_jobs().register(services.registry)
    if EXPORT_JOB not in services.registry.names():
        services.export_jobs().register(services.registry)
    if EXTRACT_JOB not in services.registry.names():
        services.extraction_jobs().register(services.registry)
    return services
