"""S8, feedback: the accepted or corrected coding becomes the supplier's newest precedent, and
its document number is recorded as used. Appending the case to the evaluation set is the
store's job."""

from decimal import Decimal

from riso.contracts import (
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
    return _remember(feedback, memory), _record_number(
        feedback.final.document.number, counters, index
    )


def _remember(feedback: Feedback, memory: SupplierMemory) -> SupplierMemory:
    ico = feedback.supplier_ico or feedback.proposal.supplier.ico
    if ico is None:
        return memory
    final = feedback.final
    precedent = Precedent(
        document_number=final.document.number,
        booking_date=final.document.booking_date,
        amount=sum((line.amount for line in final.budget), Decimal(0)),
        variable_symbol=feedback.proposal.invoice.vs,
        lines=[
            PrecedentLine(
                budget_key=budget.key,
                md=post.md,
                dal=post.dal,
                budget_text=budget.text,
                posting_text=post.text,
            )
            for post, budget in zip(final.posting, final.budget, strict=False)
        ],
        source="feedback",
    )
    suppliers = list(memory.suppliers)
    for i, record in enumerate(suppliers):
        if record.ico == ico:
            suppliers[i] = record.model_copy(update={"precedents": [precedent, *record.precedents]})
            break
    else:
        name = feedback.proposal.supplier.name or ico
        suppliers.append(SupplierRecord(ico=ico, name=name, precedents=[precedent]))
    return memory.model_copy(update={"suppliers": suppliers})


def _record_number(number: str | None, counters: Counters, index: ReferenceIndex) -> Counters:
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
