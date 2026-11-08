"""The knowledge health report of a customer and year (plan §6.5): Systém's health view and
`riso check --customer <IČO>`."""

from riso.codelists.application.conventions import customer_knowledge
from riso.codelists.application.uow import CodelistsUnitOfWork
from riso.codelists.domain import CUSTOMER_KINDS, HealthFinding, health_report
from riso.contracts import SupplierMemory
from riso.identity import Permission
from riso.shared.context import RequestContext
from riso.shared.errors import InvalidState


def knowledge_health(
    ctx: RequestContext,
    uow: CodelistsUnitOfWork,
    customer_id: str,
    year: int,
    memory: SupplierMemory,
) -> list[HealthFinding]:
    """The findings for the customer's lists, conventions and supplier memory of the year.
    Without a global knowledge base for the year, that is the one finding."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    try:
        knowledge, _ = customer_knowledge(ctx, uow, customer_id, year)
    except InvalidState:
        knowledge = None
    with uow:
        lists = {
            kind: version
            for kind in CUSTOMER_KINDS
            if (version := uow.codelists.active(customer_id, kind, year)) is not None
        }
        global_kinds = set(uow.codelists.active_ids(None, year))
    return health_report(lists, global_kinds, knowledge, memory)
