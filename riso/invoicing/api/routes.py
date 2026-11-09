"""The invoicing API. Until P2-M4 it has one route: coding a posted invoice with the
customer's data, storing nothing."""

from typing import Annotated

from fastapi import APIRouter, Depends

from riso.api.deps import Caller, ServicesDep, check_csrf, customer_context
from riso.contracts import CodingProposal, InvoiceDocument
from riso.identity import Permission
from riso.invoicing.application import code_document
from riso.shared.clock import local_date

router = APIRouter(prefix="/api", dependencies=[Depends(check_csrf)], tags=["invoicing"])


@router.post("/customers/{customer_id}/code", name="coding.code")
def code(
    caller: Annotated[Caller, Depends(customer_context(Permission.INVOICES_PROCESS))],
    services: ServicesDep,
    customer_id: str,
    body: InvoiceDocument,
) -> CodingProposal:
    """The engine's proposal for the invoice, coded with the customer's code lists,
    parameters and conventions for the invoice's booking year. Nothing is stored. (Supplier
    memory and counters come from the demo's files until P2-M4.) 409 when the customer has no
    lists or parameters for that year."""
    return code_document(
        caller.ctx,
        services.reference_data(),
        services.supplier_state(),
        customer_id,
        body,
        today=local_date(services.clock.now()),
    )
