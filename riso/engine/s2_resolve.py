"""S2, resolution: the supplier's precedents, the series (FD, or FDŠJ for the canteen), the
document number and the booking date from the handwritten note, and the counter's next
number only when the handwritten number is missing."""

from riso.contracts import Counters, EntityContext, SupplierMemory, SupplierRecord
from riso.engine.models import NormalisedInvoice, ResolvedContext
from riso.knowledge import KnowledgeBase
from riso.reference import ReferenceIndex, format_number
from riso.text import words


def resolve(
    invoice: NormalisedInvoice,
    *,
    entity: EntityContext,
    index: ReferenceIndex,
    memory: SupplierMemory,
    counters: Counters,
    knowledge: KnowledgeBase,
) -> ResolvedContext:
    issues = []
    supplier = memory.find(invoice.supplier_ico) if invoice.supplier_ico else None
    if supplier is None and invoice.supplier_ico is None:
        supplier = _by_name(invoice, memory)
        if supplier is not None:
            issues.append(f"supplier found by name, {supplier.name}; its IČO was not read")

    canteen_food = bool(invoice.concept_names() & set(knowledge.canteen.concepts))
    canteen = (
        canteen_food
        or knowledge.canteen.function in invoice.named_functions()
        or _canteen_supplier(supplier, entity)
    )
    series = entity.canteen_series if canteen else entity.default_series
    year = invoice.booking_date.year if invoice.booking_date else entity.budget_year
    pattern = index.series[series].pattern
    if invoice.handwritten_number is not None:
        number = format_number(pattern, invoice.handwritten_number, year)
        source = "handwritten"
    else:
        next_number = counters.last_used.get(f"{series}/{year}", 0) + 1
        number = format_number(pattern, next_number, year)
        source = "counter"
        issues.append(f"the handwritten number was not read; {number} is the counter's next")
    if invoice.booking_date is None:
        issues.append("the handwritten booking date was not read")

    return ResolvedContext(
        entity=entity,
        bundle_id=index.bundle.bundle_id,
        supplier=supplier,
        series=series,
        canteen=canteen,
        canteen_food=canteen_food,
        zdroj=knowledge.canteen.zdroj if canteen_food else entity.default_zdroj,
        document_number=number,
        number_source=source,
        booking_date=invoice.booking_date,
        used_numbers=frozenset(counters.used_numbers),
        issues=tuple(issues),
    )


def _by_name(invoice: NormalisedInvoice, memory: SupplierMemory) -> SupplierRecord | None:
    name = invoice.document.supplier.name
    if not name:
        return None
    return next((s for s in memory.suppliers if words(s.name) == words(name)), None)


def _canteen_supplier(supplier: SupplierRecord | None, entity: EntityContext) -> bool:
    """A supplier whose invoices went to the canteen's series before."""
    prefix = f"{entity.canteen_series}/"
    return supplier is not None and any(
        (p.document_number or "").startswith(prefix) for p in supplier.precedents
    )
