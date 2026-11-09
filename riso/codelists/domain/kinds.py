"""The kinds of code list, their scope, and the states and origins of a version (plan §6.1–6.2).

A kind's scope is fixed: the EK, COFOG, funding source and framework chart lists are global
(one per year, kept by the admin); the others belong to one customer and year.
"""

from enum import StrEnum


class ListKind(StrEnum):
    # A customer's own lists, in the order the reference bundle lists them.
    ACCOUNTS = "accounts"
    """Chart of accounts: SU and AU."""
    BUDGET_EXPENSE = "budget_expense"
    """Expense budget positions."""
    BUDGET_INCOME = "budget_income"
    """Income budget positions."""
    DOCUMENT_SERIES = "document_series"
    TRANSFERS = "transfers"
    COST_CENTRES = "cost_centres"

    # Global lists, per year.
    EK = "ek"
    """The economic classification of the budget."""
    COFOG = "cofog"
    """The functional classification: oddiel, skupina, trieda, podtrieda."""
    FUNDING_SOURCES = "funding_sources"
    """Zdroje."""
    FRAMEWORK_ACCOUNTS = "framework_accounts"
    """The framework chart of accounts for municipalities: classes, groups, synthetic accounts."""

    @property
    def is_global(self) -> bool:
        return self in GLOBAL_KINDS


CUSTOMER_KINDS: tuple[ListKind, ...] = (
    ListKind.ACCOUNTS,
    ListKind.BUDGET_EXPENSE,
    ListKind.BUDGET_INCOME,
    ListKind.DOCUMENT_SERIES,
    ListKind.TRANSFERS,
    ListKind.COST_CENTRES,
)
GLOBAL_KINDS: tuple[ListKind, ...] = (
    ListKind.EK,
    ListKind.COFOG,
    ListKind.FUNDING_SOURCES,
    ListKind.FRAMEWORK_ACCOUNTS,
)
REQUIRED_CUSTOMER_KINDS: tuple[ListKind, ...] = (
    ListKind.ACCOUNTS,
    ListKind.BUDGET_EXPENSE,
    ListKind.DOCUMENT_SERIES,
)
"""The lists the engine cannot code without. The income budget, transfers and cost centres
may be missing (the engine then sees them empty)."""


class VersionStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class VersionOrigin(StrEnum):
    """What made a version."""

    SEED = "seed"
    """`riso seed`, from the committed files."""
    IMPORT = "import"
    """An import run (P2-M3)."""
    EDIT = "edit"
    """A row edit: add, edit, deactivate."""
    COPY = "copy"
    """Copied from another customer or another year."""
