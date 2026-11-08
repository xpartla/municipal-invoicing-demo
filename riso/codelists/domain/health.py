"""The knowledge health report of a customer and year (plan §6.5): what keeps the engine from
proposing, or makes it propose something the lists do not have.

| Finding | Severity |
|---|---|
| there is no global knowledge base for the year (`knowledge/<year>/`) | error |
| a list the engine needs (chart, expense budget, series) is missing for the year | error |
| another list of the customer's is missing for the year | info |
| a global list is missing for the year | warning |
| a convention names an account the chart lacks (AU rules, the canteen debit) | warning |
| the canteen rule names a budget position the expense budget lacks | warning |
| an expense budget EK has no bridge rule, so its positions are never proposed | warning |
| a supplier precedent names a position or an account the active lists lack | warning |

Inactive rows count as missing: the engine never sees them.
"""

from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum

from riso.codelists.domain.entries import AccountEntry, BudgetEntry
from riso.codelists.domain.kinds import (
    CUSTOMER_KINDS,
    GLOBAL_KINDS,
    REQUIRED_CUSTOMER_KINDS,
    ListKind,
)
from riso.codelists.domain.version import CodeListVersion
from riso.contracts import SupplierMemory, budget_key
from riso.knowledge import KnowledgeBase


class HealthSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class HealthCode(StrEnum):
    KNOWLEDGE_MISSING = "knowledge_missing"
    LIST_MISSING = "list_missing"
    GLOBAL_LIST_MISSING = "global_list_missing"
    CONVENTION_MISSING_ACCOUNT = "convention_missing_account"
    CONVENTION_MISSING_POSITION = "convention_missing_position"
    EK_WITHOUT_BRIDGE = "ek_without_bridge"
    PRECEDENT_OUTSIDE_LISTS = "precedent_outside_lists"


@dataclass(frozen=True, slots=True)
class HealthFinding:
    code: HealthCode
    severity: HealthSeverity
    subject: str
    """What is missing or unmatched: a list kind, an account, an EK, a budget key."""
    where: str | None = None
    """Where it was named: `debit 518`, `canteen`, a supplier's IČO and document number."""
    kind: ListKind | None = None
    """The list the subject belongs to, for a link to it."""
    count: int = 1
    """How many rows it concerns (positions for an EK)."""

    @property
    def message(self) -> str:
        where = f" ({self.where})" if self.where else ""
        return f"{self.code}: {self.subject}{where}"


def _missing_lists(
    lists: Mapping[ListKind, CodeListVersion], global_kinds: Collection[ListKind]
) -> list[HealthFinding]:
    found = []
    for kind in CUSTOMER_KINDS:
        if kind not in lists:
            severity = (
                HealthSeverity.ERROR if kind in REQUIRED_CUSTOMER_KINDS else HealthSeverity.INFO
            )
            found.append(HealthFinding(HealthCode.LIST_MISSING, severity, kind.value, kind=kind))
    for kind in GLOBAL_KINDS:
        if kind not in global_kinds:
            found.append(
                HealthFinding(
                    HealthCode.GLOBAL_LIST_MISSING, HealthSeverity.WARNING, kind.value, kind=kind
                )
            )
    return found


def _conventions(
    knowledge: KnowledgeBase, accounts: frozenset[str], expense: frozenset[str]
) -> list[HealthFinding]:
    found = []
    for side, table in (("debit", knowledge.au_rules.debit), ("credit", knowledge.au_rules.credit)):
        for su, rules in table.items():
            for au in dict.fromkeys([rules.default, *(rule.au for rule in rules.rules)]):
                if f"{su} {au}" not in accounts:
                    found.append(
                        HealthFinding(
                            HealthCode.CONVENTION_MISSING_ACCOUNT,
                            HealthSeverity.WARNING,
                            f"{su} {au}",
                            f"{side} {su}",
                            ListKind.ACCOUNTS,
                        )
                    )
    canteen = knowledge.canteen
    if canteen is None:
        return found
    if canteen.md not in accounts:
        found.append(
            HealthFinding(
                HealthCode.CONVENTION_MISSING_ACCOUNT,
                HealthSeverity.WARNING,
                canteen.md,
                "canteen",
                ListKind.ACCOUNTS,
            )
        )
    oddiel, trieda = canteen.function.split()
    for analytika in [canteen.analytika, *canteen.alternatives]:
        key = budget_key(canteen.ek, canteen.zdroj, oddiel, trieda, analytika)
        if key not in expense:
            found.append(
                HealthFinding(
                    HealthCode.CONVENTION_MISSING_POSITION,
                    HealthSeverity.WARNING,
                    key,
                    "canteen",
                    ListKind.BUDGET_EXPENSE,
                )
            )
    return found


def _unbridged(positions: list[BudgetEntry], knowledge: KnowledgeBase) -> list[HealthFinding]:
    counts = Counter(p.ek for p in positions if knowledge.su_for(p.ek) is None)
    return [
        HealthFinding(
            HealthCode.EK_WITHOUT_BRIDGE,
            HealthSeverity.WARNING,
            ek,
            kind=ListKind.BUDGET_EXPENSE,
            count=count,
        )
        for ek, count in sorted(counts.items())
    ]


def _precedents(
    memory: SupplierMemory, accounts: frozenset[str], expense: frozenset[str]
) -> list[HealthFinding]:
    found = []
    for supplier in memory.suppliers:
        for precedent in supplier.precedents:
            where = f"{supplier.ico} {precedent.document_number or precedent.booking_date or ''}"
            for line in precedent.lines:
                unmatched = []
                if line.budget_key not in expense:
                    unmatched.append((line.budget_key, ListKind.BUDGET_EXPENSE))
                unmatched += [
                    (account, ListKind.ACCOUNTS)
                    for account in dict.fromkeys([line.md, line.dal])
                    if account not in accounts
                ]
                found += [
                    HealthFinding(
                        HealthCode.PRECEDENT_OUTSIDE_LISTS,
                        HealthSeverity.WARNING,
                        subject,
                        where.strip(),
                        kind,
                    )
                    for subject, kind in unmatched
                ]
    return found


def health_report(
    lists: Mapping[ListKind, CodeListVersion],
    global_kinds: Collection[ListKind],
    knowledge: KnowledgeBase | None,
    memory: SupplierMemory,
) -> list[HealthFinding]:
    """The findings for the customer's active lists of a year (`lists`, by kind), the global
    lists the year has, the knowledge merged with the customer's conventions (None when the
    year has no global knowledge), and its supplier memory. Errors first, then warnings, then
    notes."""
    accounts = frozenset(
        e.key
        for e in (lists[ListKind.ACCOUNTS].active_entries() if ListKind.ACCOUNTS in lists else ())
        if isinstance(e, AccountEntry)
    )
    positions = [
        e
        for e in (
            lists[ListKind.BUDGET_EXPENSE].active_entries()
            if ListKind.BUDGET_EXPENSE in lists
            else ()
        )
        if isinstance(e, BudgetEntry)
    ]
    expense = frozenset(p.key for p in positions)
    found = _missing_lists(lists, global_kinds)
    if knowledge is None:
        found.append(HealthFinding(HealthCode.KNOWLEDGE_MISSING, HealthSeverity.ERROR, "knowledge"))
    else:
        if ListKind.ACCOUNTS in lists and ListKind.BUDGET_EXPENSE in lists:
            found += _conventions(knowledge, accounts, expense)
        found += _unbridged(positions, knowledge)
    if ListKind.ACCOUNTS in lists and ListKind.BUDGET_EXPENSE in lists:
        found += _precedents(memory, accounts, expense)
    order = {HealthSeverity.ERROR: 0, HealthSeverity.WARNING: 1, HealthSeverity.INFO: 2}
    return sorted(found, key=lambda f: order[f.severity])
