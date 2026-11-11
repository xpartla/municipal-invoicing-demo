"""What the dashboards read from the code lists (plan §10.2, §10.8): the expense budget with
its amounts (the drawdown), the names of the functions (the breakdown by unit), and which of
the lists the engine needs a customer has for a year. Call inside the unit of work; the
caller checked its permission."""

from dataclasses import dataclass
from decimal import Decimal

from riso.codelists.application.uow import CodelistsUnitOfWork
from riso.codelists.domain import REQUIRED_CUSTOMER_KINDS, BudgetEntry, CofogEntry, ListKind


@dataclass(frozen=True, slots=True)
class BudgetAmountView:
    key: str
    description: str | None
    approved: Decimal | None
    adjusted: Decimal | None

    @property
    def budgeted(self) -> Decimal | None:
        """The adjusted budget when there is one, else the approved."""
        return self.adjusted if self.adjusted is not None else self.approved


def expense_budget(
    uow: CodelistsUnitOfWork, customer_id: str, year: int
) -> tuple[BudgetAmountView, ...]:
    """The active positions of the customer's expense budget of the year (none without
    one)."""
    version = uow.codelists.active(customer_id, ListKind.BUDGET_EXPENSE, year)
    if version is None:
        return ()
    return tuple(
        BudgetAmountView(e.key, e.description, e.approved, e.adjusted)
        for e in version.entries
        if isinstance(e, BudgetEntry) and e.active
    )


def function_names(uow: CodelistsUnitOfWork, year: int) -> dict[str, tuple[str, str]]:
    """`oddiel trieda` as a budget key writes it (`09 111`) → the COFOG code and name of the
    year's global list (`09.1.1.1`, `Predprimárne vzdelávanie s bežnou starostlivosťou`)."""
    version = uow.codelists.active(None, ListKind.COFOG, year)
    if version is None:
        return {}
    found: dict[str, tuple[str, str]] = {}
    for entry in version.entries:
        if isinstance(entry, CofogEntry) and entry.trieda is not None:
            found.setdefault(f"{entry.oddiel} {entry.trieda}", (entry.code, entry.name))
    return found


def missing_required_lists(uow: CodelistsUnitOfWork, customer_id: str, year: int) -> list[str]:
    """The lists the engine cannot code without that the customer has no active version of
    for the year (`accounts`, `budget_expense`, `document_series`)."""
    return [
        kind.value
        for kind in REQUIRED_CUSTOMER_KINDS
        if uow.codelists.active(customer_id, kind, year) is None
    ]
