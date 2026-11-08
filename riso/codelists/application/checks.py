"""A customer's lists for a year checked against the global lists of that year (plan §6.3)."""

from riso.codelists.application.uow import CodelistsUnitOfWork
from riso.codelists.domain import (
    CUSTOMER_KINDS,
    GLOBAL_KINDS,
    Finding,
    GlobalLists,
    validate_lists,
)
from riso.identity import Permission
from riso.shared.context import RequestContext


def global_lists(uow: CodelistsUnitOfWork, year: int) -> GlobalLists:
    """The year's active global lists; call inside the unit of work."""
    versions = {}
    for kind in GLOBAL_KINDS:
        version = uow.codelists.active(None, kind, year)
        if version is not None:
            versions[kind] = version
    return GlobalLists.of(year, versions)


def customer_findings(
    ctx: RequestContext, uow: CodelistsUnitOfWork, customer_id: str, year: int
) -> list[Finding]:
    """The findings of every active list of the customer's for the year."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        lists = global_lists(uow, year)
        versions = [
            version
            for kind in CUSTOMER_KINDS
            if (version := uow.codelists.active(customer_id, kind, year)) is not None
        ]
    return validate_lists(versions, lists)
