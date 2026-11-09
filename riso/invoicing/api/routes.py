"""The invoicing API: coding a posted invoice without storing it, and the number series."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from riso.api.deps import Caller, ServicesDep, check_csrf, customer_context
from riso.contracts import CodingProposal, InvoiceDocument
from riso.identity import Permission
from riso.invoicing.api.models import LastUsedIn, NumberSeriesListOut, NumberSeriesOut
from riso.invoicing.application import code_document, list_series, set_last_used
from riso.shared.clock import local_date

router = APIRouter(prefix="/api", dependencies=[Depends(check_csrf)], tags=["invoicing"])

Year = Annotated[int | None, Query(ge=2000, le=2100, description="Default: this year")]


@router.post("/customers/{customer_id}/code", name="coding.code")
def code(
    caller: Annotated[Caller, Depends(customer_context(Permission.INVOICES_PROCESS))],
    services: ServicesDep,
    customer_id: str,
    body: InvoiceDocument,
) -> CodingProposal:
    """The engine's proposal for the invoice, coded with the customer's code lists,
    parameters and conventions for the invoice's booking year, and its supplier memory and
    counters. Nothing is stored. 409 when the customer has no lists or parameters for that
    year."""
    return code_document(
        caller.ctx,
        services.reference_data(),
        services.supplier_state(),
        customer_id,
        body,
        today=local_date(services.clock.now()),
    )


@router.get("/customers/{customer_id}/number-series", name="number_series.list")
def number_series(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
    year: Year = None,
) -> NumberSeriesListOut:
    """The year's number series (plan §7.2): those of the document series list, used or
    not, then any other with a counter; each with its counter, the next number, the numbers
    held and the gaps between them."""
    chosen = year or local_date(services.clock.now()).year
    views = list_series(caller.ctx, services.uow(immediate=False), customer_id, chosen)
    return NumberSeriesListOut(year=chosen, items=[NumberSeriesOut.of(v) for v in views])


@router.put(
    "/customers/{customer_id}/number-series/{series}/{year}", name="number_series.set_last_used"
)
def set_number_series_last_used(
    caller: Annotated[Caller, Depends(customer_context(Permission.CODELISTS_EDIT))],
    services: ServicesDep,
    customer_id: str,
    series: Annotated[str, Path(max_length=16)],
    year: Annotated[int, Path(ge=2000, le=2100)],
    body: LastUsedIn,
) -> NumberSeriesOut:
    """Edits the counter (audited), until it syncs with TOPSET. 422 below a number held;
    404 for a series the year's list does not have."""
    view = set_last_used(caller.ctx, services.uow(), customer_id, series, year, body.last_used)
    return NumberSeriesOut.of(view)
