"""S6, validation: the invariants of plan section 4.

The dictionary checks are built: they hold the anchor cases and the seeded supplier memory to
the reference data. The proposal-level checks come with the rest of the engine in M1."""

from decimal import Decimal

from riso.contracts import Coding, Validation
from riso.engine.models import NormalisedInvoice, ResolvedContext
from riso.reference import ReferenceIndex, parse_number

SUPPLIER_SU = "321"


def check_codes(md: str, dal: str, budget_key: str, index: ReferenceIndex) -> list[str]:
    """Errors for one posting line and its budget line: the codes exist, the debit fits the
    economic class and the credit is a supplier account."""
    return _missing_codes(md, dal, budget_key, index) + _account_type_errors(
        md, dal, budget_key, index
    )


def check_coding(
    coding: Coding, index: ReferenceIndex, *, gross: Decimal | None = None
) -> Validation:
    """The dictionary invariants of a complete coding. Each budget line pairs with the posting
    line at the same position, as the per-entry split of plan section 5 produces them."""
    pairs = list(zip(coding.posting, coding.budget, strict=False))
    results = {
        "document series": _document_errors(coding, index),
        "lines pair up": _pairing_errors(coding),
        "keys exist": [
            error
            for post, budget in pairs
            for error in _missing_codes(post.md, post.dal, budget.key, index)
        ],
        "account types": [
            error
            for post, budget in pairs
            for error in _account_type_errors(post.md, post.dal, budget.key, index)
        ],
        "references exist": _reference_errors(coding, index),
        "sums match": _sum_errors(coding, gross),
    }
    errors = [error for found in results.values() for error in found]
    return Validation(
        ok=not errors,
        checks=[name for name, found in results.items() if not found],
        errors=list(dict.fromkeys(errors)),
    )


def validate(
    invoice: NormalisedInvoice, context: ResolvedContext, coding: Coding, index: ReferenceIndex
) -> Validation:
    """check_coding plus period sanity, duplicates by supplier and variable symbol and by
    document number, transfer expectations and split coverage."""
    raise NotImplementedError("S6 beyond the dictionary checks is built in M1")


def _missing_codes(md: str, dal: str, budget_key: str, index: ReferenceIndex) -> list[str]:
    errors = [
        f"{side} {key} is not in the chart of accounts"
        for side, key in (("MD", md), ("DAL", dal))
        if key not in index.accounts
    ]
    if budget_key not in index.expense:
        errors.append(f"budget position {budget_key} is not in the approved budget")
    return errors


def _account_type_errors(md: str, dal: str, budget_key: str, index: ReferenceIndex) -> list[str]:
    """Debit: a cost account for EK 6xx, an acquisition account 04x for EK 7xx, a liability
    for EK 8xx. Credit: a supplier account 321."""
    errors = []
    debit, credit = index.accounts.get(md), index.accounts.get(dal)
    position = index.expense.get(budget_key)
    if debit is not None and position is not None:
        ek, ek_class = position.ek, position.ek[0]
        if ek_class == "6" and debit.type != "cost":
            errors.append(f"MD {md} is not a cost account, as current expense EK {ek} needs")
        elif ek_class == "7" and not debit.su.startswith("04"):
            errors.append(f"MD {md} is not an acquisition account 04x, as capital EK {ek} needs")
        elif ek_class == "8" and debit.type != "passive":
            errors.append(f"MD {md} is not a liability, as financial operation EK {ek} needs")
    if credit is not None and credit.su != SUPPLIER_SU:
        errors.append(f"DAL {dal} is not a supplier account {SUPPLIER_SU}")
    return errors


def _document_errors(coding: Coding, index: ReferenceIndex) -> list[str]:
    document = coding.document
    series = index.series.get(document.series)
    if series is None:
        return [f"series {document.series} is not among the document series"]
    if document.number is None:
        return []
    parsed = parse_number(series.pattern, document.number)
    if parsed is None:
        return [f"number {document.number} does not follow the pattern {series.pattern}"]
    booking = document.booking_date
    if booking is not None and parsed.year is not None and parsed.year != booking.year % 100:
        return [f"number {document.number} belongs to another year than booking date {booking}"]
    return []


def _pairing_errors(coding: Coding) -> list[str]:
    if len(coding.posting) != len(coding.budget):
        return [
            f"{len(coding.posting)} posting lines against {len(coding.budget)} budget lines; "
            "every budget line has its own posting line"
        ]
    return [
        f"line {n}: posting amount {post.amount} differs from budget amount {budget.amount}"
        for n, (post, budget) in enumerate(zip(coding.posting, coding.budget, strict=True), 1)
        if post.amount != budget.amount
    ]


def _reference_errors(coding: Coding, index: ReferenceIndex) -> list[str]:
    errors = []
    for line in [*coding.posting, *coding.budget]:
        if line.stredisko is not None and line.stredisko not in index.cost_centres:
            errors.append(f"stredisko {line.stredisko} is not in the list")
        if line.transfer is not None and line.transfer not in index.transfers:
            errors.append(f"transfer {line.transfer} is not in the list")
    return errors


def _sum_errors(coding: Coding, gross: Decimal | None) -> list[str]:
    posting = sum((line.amount for line in coding.posting), Decimal(0))
    budget = sum((line.amount for line in coding.budget), Decimal(0))
    errors = []
    if posting != budget:
        errors.append(f"posting lines sum to {posting}, budget lines to {budget}")
    if gross is not None and budget != gross:
        errors.append(f"budget lines sum to {budget}, the invoice gross is {gross}")
    return errors
