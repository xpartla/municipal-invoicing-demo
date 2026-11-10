"""Enriching an extraction (plan §8.2 step 5): the supplier's name from the customer's
supplier memory when the OCR missed it or read it doubtfully. Only a validated IČO is looked
up; the memory holds names, not addresses."""

from typing import Protocol

from riso.intake.domain.extract import TRUSTED, Extracted


class SupplierNames(Protocol):
    def name_of(self, customer_id: str, ico: str) -> str | None:
        """The supplier's name in the customer's supplier memory, if it has booked from it."""
        ...


def enrich(extracted: Extracted, customer_id: str, suppliers: SupplierNames) -> Extracted:
    document = extracted.document
    confidence = document.ocr_meta.confidence
    ico = document.supplier.ico
    if not ico or confidence.get("supplier.ico", 0.0) < TRUSTED:
        return extracted
    if document.supplier.name and confidence.get("supplier.name", 0.0) >= TRUSTED:
        return extracted
    name = suppliers.name_of(customer_id, ico)
    if name is None or name == document.supplier.name:
        return extracted
    meta = document.ocr_meta.model_copy(
        update={"confidence": {**confidence, "supplier.name": 0.95}}
    )
    enriched = document.model_copy(
        update={"supplier": document.supplier.model_copy(update={"name": name}), "ocr_meta": meta}
    )
    evidence = {p: e for p, e in extracted.evidence.items() if p != "supplier.name"}
    return Extracted(enriched, evidence, (*extracted.warnings, "supplier_name_from_memory"))
