"""Lookups over one reference bundle, built when the bundle is loaded (plan stage S0)."""

from collections import defaultdict

from riso.contracts import (
    Account,
    BudgetPosition,
    CostCentre,
    DocumentSeries,
    ReferenceBundle,
    Transfer,
)


class ReferenceIndex:
    def __init__(self, bundle: ReferenceBundle) -> None:
        self.bundle = bundle
        self.accounts: dict[str, Account] = {a.key: a for a in bundle.accounts}
        self.expense: dict[str, BudgetPosition] = {
            p.key: p for p in bundle.budget_positions_expense
        }
        self.income: dict[str, BudgetPosition] = {p.key: p for p in bundle.budget_positions_income}
        self.series: dict[str, DocumentSeries] = {s.code: s for s in bundle.document_series}
        self.transfers: dict[str, Transfer] = {t.id: t for t in bundle.transfers}
        self.cost_centres: dict[str, CostCentre] = {c.code: c for c in bundle.cost_centres}

        self.accounts_by_su: dict[str, list[Account]] = defaultdict(list)
        for account in bundle.accounts:
            self.accounts_by_su[account.su].append(account)
        self.expense_by_ek: dict[str, list[BudgetPosition]] = defaultdict(list)
        for position in bundle.budget_positions_expense:
            self.expense_by_ek[position.ek].append(position)
        self.transfers_by_zdroj: dict[str, list[Transfer]] = defaultdict(list)
        for transfer in bundle.transfers:
            self.transfers_by_zdroj[transfer.zdroj].append(transfer)
