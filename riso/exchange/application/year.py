"""Starting a customer's new year from the previous one (plan §6.6, P2-M8-T08).

A year's code lists, parameters and conventions belong to that year. When the next year comes,
the customer takes what the previous year has and the new one lacks: each list as version 1 of
the new year (origin `copy`), the parameters, the conventions. What the new year already has
stays; the number series are not copied, so they start at 0 unless set (§6.6). The copy is
small (a list holds hundreds of rows), so it runs in the request, not as a job. Audited.
"""

from dataclasses import dataclass

from riso.codelists import copy_conventions, copy_lists
from riso.exchange.application.copy import MAX_YEAR, MIN_YEAR, CopyUnitOfWork
from riso.identity import Permission
from riso.shared.context import RequestContext
from riso.shared.errors import InvalidState, ValidationFailed
from riso.tenancy import copy_parameters


@dataclass(frozen=True, slots=True)
class YearCarriedOver:
    year: int
    from_year: int
    code_lists: list[str]
    """The kinds of the lists the new year got."""
    parameters: bool
    conventions: bool


def carry_year_over(
    ctx: RequestContext, uow: CopyUnitOfWork, customer_id: str, year: int
) -> YearCarriedOver:
    """Gives `year` what `year - 1` has and `year` lacks. Refused when there is nothing to
    take: the previous year has nothing, or the new year has everything already."""
    ctx.require(Permission.CODELISTS_EDIT, customer_id)
    if not MIN_YEAR < year <= MAX_YEAR:
        raise ValidationFailed.on("year", f"between {MIN_YEAR + 1} and {MAX_YEAR}", "year")
    previous = year - 1
    with uow:
        uow.customers.get(customer_id)
        versions = copy_lists(ctx, uow, customer_id, customer_id, previous, into_year=year)
        parameters = copy_parameters(ctx, uow, customer_id, customer_id, previous, into_year=year)
        conventions = copy_conventions(ctx, uow, customer_id, customer_id, previous, into_year=year)
        if not versions and not parameters and not conventions:
            raise InvalidState(f"{previous} has nothing that {year} lacks")
        done = YearCarriedOver(
            year,
            previous,
            sorted(v.kind.value for v in versions),
            parameters,
            conventions,
        )
        uow.audit.record(
            ctx,
            "codelists.year_carried_over",
            target_type="customer",
            target_id=customer_id,
            customer_id=customer_id,
            details={
                "year": year,
                "from_year": previous,
                "code_lists": done.code_lists,
                "parameters": parameters,
                "conventions": conventions,
            },
        )
        uow.commit()
    return done
