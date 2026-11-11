"""What the dashboards read from the code lists (plan §10.2, §10.8): the expense budget with
its amounts (the drawdown), the names of the functions (the breakdown by unit), the lists the
engine needs that a customer lacks for a year, and the errors of the knowledge health report.
Call inside the unit of work; the caller checked its permission.

Domov is the page customer users land on, so these stay cheap: a version never changes once
made (an edit makes a new one, plan §6.2), so what is read from a version is cached by its ID,
and the health report's errors (plan §6.5: no global knowledge base for the year, or a list the
engine needs is missing) are found from the active versions' IDs without reading their
entries."""

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from threading import Lock

from riso.codelists.application.uow import CodelistsUnitOfWork
from riso.codelists.domain import (
    REQUIRED_CUSTOMER_KINDS,
    BudgetEntry,
    CodeListVersion,
    CofogEntry,
    HealthCode,
    HealthFinding,
    HealthSeverity,
    ListKind,
)
from riso.knowledge import UnknownKnowledge, load_knowledge


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


class VersionReadCache[T]:
    """What was read from a version, by the version's ID (the most recent ones). Concurrent
    requests for a version not read yet wait for the one that reads it."""

    def __init__(self, size: int = 64) -> None:
        self._size = size
        self._found: OrderedDict[str, T] = OrderedDict()
        self._lock = Lock()
        self._loading: dict[str, Lock] = {}

    def _cached(self, version_id: str) -> tuple[T] | None:
        """The stored value, in a 1-tuple; None when it is not stored."""
        with self._lock:
            if version_id in self._found:
                self._found.move_to_end(version_id)
                return (self._found[version_id],)
            return None

    def read(self, version_id: str, load: Callable[[], T]) -> T:
        hit = self._cached(version_id)
        if hit is not None:
            return hit[0]
        with self._lock:
            loading = self._loading.setdefault(version_id, Lock())
        with loading:
            hit = self._cached(version_id)
            if hit is not None:
                return hit[0]
            loaded = load()
            with self._lock:
                self._found[version_id] = loaded
                self._loading.pop(version_id, None)
                while len(self._found) > self._size:
                    self._found.popitem(last=False)
        return loaded

    def clear(self) -> None:
        with self._lock:
            self._found.clear()


BUDGETS: VersionReadCache[tuple[BudgetAmountView, ...]] = VersionReadCache()
FUNCTIONS: VersionReadCache[dict[str, tuple[str, str]]] = VersionReadCache()


def _budget(version: CodeListVersion) -> tuple[BudgetAmountView, ...]:
    return tuple(
        BudgetAmountView(e.key, e.description, e.approved, e.adjusted)
        for e in version.entries
        if isinstance(e, BudgetEntry) and e.active
    )


def _functions(version: CodeListVersion) -> dict[str, tuple[str, str]]:
    found: dict[str, tuple[str, str]] = {}
    for entry in version.entries:
        if isinstance(entry, CofogEntry) and entry.trieda is not None:
            found.setdefault(f"{entry.oddiel} {entry.trieda}", (entry.code, entry.name))
    return found


def expense_budget(
    uow: CodelistsUnitOfWork, customer_id: str, year: int
) -> tuple[BudgetAmountView, ...]:
    """The active positions of the customer's expense budget of the year (none without
    one)."""
    version_id = uow.codelists.active_ids(customer_id, year).get(ListKind.BUDGET_EXPENSE)
    if version_id is None:
        return ()
    return BUDGETS.read(version_id, lambda: _budget(uow.codelists.get(customer_id, version_id)))


def function_names(uow: CodelistsUnitOfWork, year: int) -> dict[str, tuple[str, str]]:
    """`oddiel trieda` as a budget key writes it (`09 111`) → the COFOG code and name of the
    year's global list (`09.1.1.1`, `Predprimárne vzdelávanie s bežnou starostlivosťou`)."""
    version_id = uow.codelists.active_ids(None, year).get(ListKind.COFOG)
    if version_id is None:
        return {}
    return FUNCTIONS.read(version_id, lambda: _functions(uow.codelists.get(None, version_id)))


def missing_required_lists(uow: CodelistsUnitOfWork, customer_id: str, year: int) -> list[str]:
    """The lists the engine cannot code without that the customer has no active version of
    for the year (`accounts`, `budget_expense`, `document_series`)."""
    present = uow.codelists.active_ids(customer_id, year)
    return [kind.value for kind in REQUIRED_CUSTOMER_KINDS if kind not in present]


def health_errors(uow: CodelistsUnitOfWork, customer_id: str, year: int) -> list[HealthFinding]:
    """The error findings of the knowledge health report (plan §6.5), as `knowledge_health`
    gives them: no global knowledge base for the year, and each list the engine needs that is
    missing."""
    found = [
        HealthFinding(HealthCode.LIST_MISSING, HealthSeverity.ERROR, kind, kind=ListKind(kind))
        for kind in missing_required_lists(uow, customer_id, year)
    ]
    try:
        load_knowledge(year)
    except UnknownKnowledge:
        found.append(HealthFinding(HealthCode.KNOWLEDGE_MISSING, HealthSeverity.ERROR, "knowledge"))
    return found
