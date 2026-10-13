"""S8, feedback: the accepted or corrected coding becomes the supplier's newest precedent, and
its document number is recorded as used. Appending the case to the evaluation set is the
store's job."""

from decimal import Decimal

from riso.contracts import (
    Coding,
    Counters,
    Feedback,
    Precedent,
    PrecedentLine,
    SupplierMemory,
    SupplierRecord,
)
from riso.reference import ReferenceIndex, parse_number


def apply_feedback(
    feedback: Feedback, memory: SupplierMemory, counters: Counters, index: ReferenceIndex
) -> tuple[SupplierMemory, Counters]:
    ico = feedback.supplier_ico or feedback.proposal.supplier.ico
    if ico is not None:
        memory = add_precedent(
            memory,
            ico=ico,
            name=feedback.proposal.supplier.name or ico,
            coding=feedback.final,
            variable_symbol=feedback.proposal.invoice.vs,
        )
    return memory, record_number(feedback.final.document.number, counters, index)


def add_precedent(
    memory: SupplierMemory, *, ico: str, name: str, coding: Coding, variable_symbol: str | None
) -> SupplierMemory:
    """The coding becomes the supplier's newest precedent."""
    precedent = Precedent(
        document_number=coding.document.number,
        booking_date=coding.document.booking_date,
        amount=sum((line.amount for line in coding.budget), Decimal(0)),
        variable_symbol=variable_symbol,
        lines=[
            PrecedentLine(
                budget_key=budget.key,
                md=post.md,
                dal=post.dal,
                budget_text=budget.text,
                posting_text=post.text,
            )
            for post, budget in zip(coding.posting, coding.budget, strict=False)
        ],
        source="feedback",
    )
    suppliers = list(memory.suppliers)
    for i, record in enumerate(suppliers):
        if record.ico == ico:
            suppliers[i] = record.model_copy(update={"precedents": [precedent, *record.precedents]})
            break
    else:
        suppliers.append(SupplierRecord(ico=ico, name=name, precedents=[precedent]))
    return memory.model_copy(update={"suppliers": suppliers})


def record_number(number: str | None, counters: Counters, index: ReferenceIndex) -> Counters:
    """Marks the number used and moves the series' counter past it."""
    if number is None:
        return counters
    code = number.split("/")[0]
    series = index.series.get(code)
    parsed = parse_number(series.pattern, number) if series else None
    last_used = dict(counters.last_used)
    if parsed is not None and parsed.year is not None:
        key = f"{code}/{2000 + parsed.year}"
        last_used[key] = max(last_used.get(key, 0), parsed.sequence)
    used = counters.used_numbers
    if number not in used:
        used = [*used, number]
    return counters.model_copy(update={"last_used": last_used, "used_numbers": used})
