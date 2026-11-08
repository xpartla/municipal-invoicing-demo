"""The codelists API: a customer's code lists, conventions and their health
(`/api/customers/{customer_id}/…`), and the global lists (`/api/admin/…`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from riso.api.composition import Services
from riso.api.deps import Caller, ServicesDep, check_csrf, customer_context, platform_context
from riso.codelists.api.models import (
    ChecklistYearOut,
    ConventionsIn,
    ConventionsOut,
    DiffOut,
    EntryIn,
    EntryPageOut,
    HealthReportOut,
    ListsOverviewOut,
    VersionOut,
    VersionRefIn,
)
from riso.codelists.application import get_conventions, knowledge_health, set_conventions
from riso.codelists.application.lists import (
    MAX_PAGE,
    AddEntry,
    Change,
    DeactivateEntry,
    EditEntry,
    ReactivateEntry,
    edit_list,
    global_checklist,
    list_entries,
    list_versions,
    lists_overview,
    version_difference,
)
from riso.codelists.domain import ListKind
from riso.identity import Permission
from riso.shared.clock import local_date
from riso.shared.errors import ValidationFailed

router = APIRouter(prefix="/api", dependencies=[Depends(check_csrf)], tags=["codelists"])

Year = Annotated[int | None, Query(ge=2000, le=2100, description="Default: this year")]


@router.get("/customers/{customer_id}/health", name="codelists.health")
def health(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
    year: Year = None,
) -> HealthReportOut:
    """The knowledge health report (plan §6.5): missing lists, conventions naming missing
    accounts, budget EKs without a bridge rule, precedents outside the active lists."""
    chosen = year or local_date(services.clock.now()).year
    memory = services.supplier_state().memory(customer_id)
    findings = knowledge_health(
        caller.ctx, services.uow(immediate=False), customer_id, chosen, memory
    )
    return HealthReportOut.of(chosen, findings)


Kind = Annotated[ListKind, Path(description="The list: accounts, budget_expense, …")]
VersionQuery = Annotated[str | None, Query(alias="version", description="Default: the active one")]
Page = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=MAX_PAGE)]


def _year(services: Services, year: int | None) -> int:
    return year or local_date(services.clock.now()).year


@router.get("/customers/{customer_id}/codelists", name="codelists.overview")
def overview(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
    year: Year = None,
) -> ListsOverviewOut:
    """The customer's lists for the year, each with its active version."""
    found = lists_overview(
        caller.ctx, services.uow(immediate=False), customer_id, _year(services, year)
    )
    return ListsOverviewOut.of(found)


@router.get("/customers/{customer_id}/codelists/{kind}/entries", name="codelists.entries")
def entries(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
    kind: Kind,
    year: Year = None,
    version: VersionQuery = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    active: bool | None = None,
    page: Page = 1,
    size: Size = 50,
) -> EntryPageOut:
    """A page of the list's entries in their order. `q` searches the key and the text fields
    regardless of case and diacritics."""
    found = list_entries(
        caller.ctx,
        services.uow(immediate=False),
        customer_id,
        kind,
        _year(services, year),
        version_id=version,
        query=q,
        active=active,
        page=page,
        size=size,
    )
    return EntryPageOut.of(found)


@router.get("/customers/{customer_id}/codelists/{kind}/versions", name="codelists.versions")
def versions(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
    kind: Kind,
    year: Year = None,
) -> list[VersionOut]:
    """The list's versions for the year, the newest first."""
    found = list_versions(
        caller.ctx, services.uow(immediate=False), customer_id, kind, _year(services, year)
    )
    return [VersionOut.of(v) for v in found]


@router.get("/customers/{customer_id}/codelists/{kind}/diff", name="codelists.diff")
def diff(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
    kind: Kind,
    old: Annotated[str, Query(description="The older version's ID")],
    new: Annotated[str, Query(description="The newer version's ID")],
) -> DiffOut:
    """Entries added, removed and changed from one version to another."""
    found = version_difference(
        caller.ctx, services.uow(immediate=False), customer_id, kind, old, new
    )
    return DiffOut.of(found)


def _edit(
    caller: Caller,
    services: Services,
    customer_id: str,
    kind: ListKind,
    year: int | None,
    change: Change,
    version_id: str | None,
) -> VersionOut:
    try:
        made = edit_list(
            caller.ctx,
            services.uow(),
            customer_id,
            kind,
            _year(services, year),
            change,
            version_id=version_id,
        )
    except ValidationFailed as exc:
        raise exc.under("values") from exc
    return VersionOut.of(made)


EditAccess = Annotated[Caller, Depends(customer_context(Permission.CODELISTS_EDIT))]


@router.post(
    "/customers/{customer_id}/codelists/{kind}/entries",
    name="codelists.add_entry",
    status_code=201,
)
def add_entry(
    caller: EditAccess,
    services: ServicesDep,
    customer_id: str,
    kind: Kind,
    body: EntryIn,
    year: Year = None,
) -> VersionOut:
    """Adds a row: a new version of the list. 409 when another edit came first."""
    return _edit(caller, services, customer_id, kind, year, AddEntry(body.values), body.version_id)


@router.put("/customers/{customer_id}/codelists/{kind}/entries/{key}", name="codelists.edit_entry")
def edit_entry(
    caller: EditAccess,
    services: ServicesDep,
    customer_id: str,
    kind: Kind,
    key: str,
    body: EntryIn,
    year: Year = None,
) -> VersionOut:
    """Changes a row's fields (those given): a new version of the list."""
    change = EditEntry(key, body.values)
    return _edit(caller, services, customer_id, kind, year, change, body.version_id)


@router.post(
    "/customers/{customer_id}/codelists/{kind}/entries/{key}/deactivate",
    name="codelists.deactivate_entry",
)
def deactivate_entry(
    caller: EditAccess,
    services: ServicesDep,
    customer_id: str,
    kind: Kind,
    key: str,
    body: VersionRefIn,
    year: Year = None,
) -> VersionOut:
    """Deactivates a row: it stays in the new version, the engine no longer sees it."""
    change = DeactivateEntry(key)
    return _edit(caller, services, customer_id, kind, year, change, body.version_id)


@router.post(
    "/customers/{customer_id}/codelists/{kind}/entries/{key}/reactivate",
    name="codelists.reactivate_entry",
)
def reactivate_entry(
    caller: EditAccess,
    services: ServicesDep,
    customer_id: str,
    kind: Kind,
    key: str,
    body: VersionRefIn,
    year: Year = None,
) -> VersionOut:
    change = ReactivateEntry(key)
    return _edit(caller, services, customer_id, kind, year, change, body.version_id)


@router.get("/customers/{customer_id}/conventions", name="conventions.get")
def conventions_get(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
    year: Year = None,
) -> ConventionsOut:
    """The customer's coding conventions for the year (revision 0 and empty while none)."""
    found = get_conventions(
        caller.ctx, services.uow(immediate=False), customer_id, _year(services, year)
    )
    return ConventionsOut.of(found)


@router.put("/customers/{customer_id}/conventions", name="conventions.set")
def conventions_set(
    caller: EditAccess,
    services: ServicesDep,
    customer_id: str,
    body: ConventionsIn,
    year: Year = None,
) -> ConventionsOut:
    """Replaces the conventions for the year; 409 when someone saved since `revision`, 422
    with the field when the document does not validate."""
    try:
        found = set_conventions(
            caller.ctx,
            services.uow(),
            customer_id,
            _year(services, year),
            body.document,
            expected_revision=body.revision,
        )
    except ValidationFailed as exc:
        raise exc.under("document") from exc
    return ConventionsOut.of(found)


# The global lists (admin) -----------------------------------------------------------------

GlobalAccess = Annotated[Caller, Depends(platform_context(Permission.GLOBAL_CODELISTS))]


@router.get("/admin/codelists", name="admin_codelists.checklist")
def checklist(caller: GlobalAccess, services: ServicesDep) -> list[ChecklistYearOut]:
    """Which global lists exist for which year: every year with one, this year and the next."""
    this_year = local_date(services.clock.now()).year
    found = global_checklist(caller.ctx, services.uow(immediate=False), this_year=this_year)
    return [ChecklistYearOut.of(y) for y in found]


@router.get("/admin/codelists/{kind}/entries", name="admin_codelists.entries")
def global_entries(
    caller: GlobalAccess,
    services: ServicesDep,
    kind: Kind,
    year: Year = None,
    version: VersionQuery = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Page = 1,
    size: Size = 50,
) -> EntryPageOut:
    found = list_entries(
        caller.ctx,
        services.uow(immediate=False),
        None,
        kind,
        _year(services, year),
        version_id=version,
        query=q,
        page=page,
        size=size,
    )
    return EntryPageOut.of(found)


@router.get("/admin/codelists/{kind}/versions", name="admin_codelists.versions")
def global_versions(
    caller: GlobalAccess, services: ServicesDep, kind: Kind, year: Year = None
) -> list[VersionOut]:
    found = list_versions(
        caller.ctx, services.uow(immediate=False), None, kind, _year(services, year)
    )
    return [VersionOut.of(v) for v in found]
