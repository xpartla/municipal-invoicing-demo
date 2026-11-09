"""Creating a customer as a copy of another (plan §9.3, P2-M3-T06).

`copy_customer` creates the new customer (as `riso.tenancy` creates any customer) and queues
the `customer_copy` job in the same transaction. The job copies, for the chosen year:

- the parameters;
- the code lists, as version 1 of each of the new customer's lists (origin `copy`);
- the conventions;
- the source customer's own mapping templates (provider and global templates are seen by
  scope anyway; plan §2 decision 59);
- the supplier memory, only when asked (off by default: analytic accounts differ between
  villages). Until P2-M4 it is the demo's file (`PrecedentSink.copy_memory`).

Invoices, number series and counters, and logins are never copied; the wizard invites the
first login through the logins API.

Permissions: creating needs `customers.create` in the target provider (staff copy into their
own provider; an admin chooses the provider or none), and the source must be one the caller
reads (staff: assigned to their provider). The job checks again with the starter's context:
reading the source and editing the new customer's code lists.

The job is idempotent: each part the target already has is left alone, so a retry after a
failure copies only what is missing. Its result says what was copied.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from riso.codelists import copy_conventions, copy_lists
from riso.exchange.application.ports import PrecedentSink
from riso.exchange.application.uow import ExchangeUnitOfWork
from riso.exchange.domain.templates import MappingTemplate, TemplateScope
from riso.identity import Permission
from riso.jobs import JobContext, JobRegistry
from riso.shared.context import RequestContext
from riso.shared.errors import NotFound, PermissionDenied, ValidationFailed
from riso.tenancy import (
    CreateCustomer,
    CustomerView,
    TenancyUnitOfWork,
    add_customer,
    copy_parameters,
)

COPY_JOB = "customer_copy"
MIN_YEAR, MAX_YEAR = 2000, 2100


class CopyUnitOfWork(ExchangeUnitOfWork, TenancyUnitOfWork, Protocol):
    """The exchange, code list and tenancy repositories on one transaction."""


class CopyOptions(BaseModel):
    """What to copy (plan §9.3 step 3), with the plan's defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    year: int = Field(ge=MIN_YEAR, le=MAX_YEAR)
    parameters: bool = True
    code_lists: bool = True
    conventions: bool = True
    templates: bool = True
    supplier_memory: bool = False


@dataclass(frozen=True, slots=True)
class CopyCustomer:
    source_id: str
    customer: CreateCustomer
    options: CopyOptions


@dataclass(frozen=True, slots=True)
class CopyStarted:
    customer: CustomerView
    job_id: str


class CopyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    target_id: str
    options: CopyOptions
    real_actor_id: str | None = None


def copy_customer(ctx: RequestContext, uow: CopyUnitOfWork, cmd: CopyCustomer) -> CopyStarted:
    """Creates the customer and queues the copy. Raises `NotFound` for a source the caller
    cannot read (its existence does not leak), and what creating a customer raises."""
    try:
        ctx.require(Permission.CUSTOMER_READ, cmd.source_id)
    except PermissionDenied:
        raise NotFound(f"no customer {cmd.source_id}") from None
    with uow:
        source = uow.customers.get(cmd.source_id)
        if source.deleted_at is not None:
            raise ValidationFailed.on("source_id", "a deleted customer", "deleted")
        customer = add_customer(ctx, uow, cmd.customer)
        payload = CopyPayload(
            source_id=cmd.source_id,
            target_id=customer.id,
            options=cmd.options,
            real_actor_id=ctx.real_actor_id,
        )
        job_id = uow.queue.enqueue(
            COPY_JOB, payload.model_dump(), customer_id=customer.id, created_by=ctx.actor_id
        )
        uow.audit.record(
            ctx,
            "customer.copy_requested",
            target_type="customer",
            target_id=customer.id,
            customer_id=customer.id,
            details={
                "source_id": cmd.source_id,
                "job_id": job_id,
                "options": cmd.options.model_dump(),
            },
        )
        uow.commit()
    return CopyStarted(customer, job_id)


def _copy_templates(
    ctx: RequestContext, uow: CopyUnitOfWork, source_id: str, target_id: str
) -> int:
    present = {
        (t.import_type, t.name) for t in uow.templates.owned(TemplateScope.CUSTOMER, target_id)
    }
    copied = 0
    for template in uow.templates.owned(TemplateScope.CUSTOMER, source_id):
        if (template.import_type, template.name) in present:
            continue
        uow.templates.add(
            MappingTemplate.create(
                uow.ids.new(),
                TemplateScope.CUSTOMER,
                target_id,
                template.name,
                template.signature,
                template.mapping,
                at=uow.clock.now(),
                actor=ctx.actor_id,
            )
        )
        copied += 1
    return copied


class CopyJobs:
    """The handler of `customer_copy`."""

    def __init__(self, uow: Callable[[], CopyUnitOfWork], precedents: PrecedentSink) -> None:
        self._uow = uow
        self._state = precedents

    def register(self, registry: JobRegistry) -> JobRegistry:
        registry.register(COPY_JOB, CopyPayload, self.copy)
        return registry

    def copy(self, payload: CopyPayload, job: JobContext) -> dict[str, Any]:
        ctx = replace(
            job.request, customer_id=payload.target_id, real_actor_id=payload.real_actor_id
        )
        source, target, options = payload.source_id, payload.target_id, payload.options
        ctx.require(Permission.CUSTOMER_READ, source)
        ctx.require(Permission.CODELISTS_EDIT, target)
        year = options.year
        result: dict[str, Any] = {"year": year}
        if options.supplier_memory:
            result["suppliers"] = self._state.copy_memory(source, target)
        with self._uow() as uow:
            uow.customers.get(target)
            if options.parameters:
                result["parameters"] = copy_parameters(ctx, uow, source, target, year)
            if options.code_lists:
                versions = copy_lists(ctx, uow, source, target, year)
                result["code_lists"] = sorted(v.kind.value for v in versions)
            if options.conventions:
                result["conventions"] = copy_conventions(ctx, uow, source, target, year)
            if options.templates:
                result["templates"] = _copy_templates(ctx, uow, source, target)
            uow.audit.record(
                ctx,
                "customer.copied",
                target_type="customer",
                target_id=target,
                customer_id=target,
                details={"source_id": source, "job_id": job.job_id, **result},
            )
            uow.commit()
        return result
