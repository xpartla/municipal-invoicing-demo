"""S7, explanation: evidence and confidence per field. A proposal needs review when any coding
field is below the threshold, a stage raised an issue, or validation warned or failed; the
reasons say which."""

from decimal import Decimal

from riso.contracts import (
    Alternative,
    CodingProposal,
    Confidence,
    DocumentRef,
    Evidence,
    InvoiceSummary,
    SupplierRef,
    Validation,
)
from riso.engine.models import (
    Candidate,
    CandidateSet,
    Decision,
    Derivation,
    NormalisedInvoice,
    ResolvedContext,
)
from riso.engine.s5_posting import debit_account
from riso.knowledge import KnowledgeBase
from riso.reference import ReferenceIndex

REVIEW_BELOW = 0.75
CODE_FIELDS = ("ek", "cofog", "zdroj", "analytika", "md", "dal")


def explain(
    invoice: NormalisedInvoice,
    context: ResolvedContext,
    candidates: CandidateSet,
    decision: Decision,
    derivation: Derivation,
    validation: Validation,
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
) -> CodingProposal:
    coding = derivation.coding
    fields = _field_confidence(invoice, context, candidates, decision, derivation, index, knowledge)
    grant_sources = frozenset(t.zdroj for t in index.bundle.transfers)
    reasons = [
        *decision.reasons,
        *_header_reasons(invoice, context),
        *validation.errors,
        *validation.warnings,
        *(
            f"zdroj {line.zdroj} is a grant source; confirm the transfer {line.transfer}"
            for line in coding.budget
            if line.transfer is not None and knowledge.expects_transfer(line.zdroj, grant_sources)
        ),
        *(
            f"{name} confidence is {fields[name]:.2f}"
            for name in CODE_FIELDS
            if fields[name] < REVIEW_BELOW
        ),
    ]
    evidence = [
        *_header_evidence(invoice, context),
        candidates.function_evidence,
        *(e for line in decision.lines for e in line.candidate.evidence),
        *derivation.evidence,
    ]
    overall = min(fields[name] for name in CODE_FIELDS)  # the weakest coding field
    return CodingProposal(
        invoice_id=invoice.document.id,
        bundle_id=context.bundle_id,
        document=coding.document,
        supplier=_supplier(invoice, context),
        invoice=_summary(invoice),
        posting=coding.posting,
        budget=coding.budget,
        confidence=Confidence(
            overall=round(overall, 2), **{name: round(value, 2) for name, value in fields.items()}
        ),
        evidence=_unique(evidence),
        alternatives=_alternatives(decision, invoice, context, index, knowledge),
        validation=validation,
        needs_review=bool(reasons),
        review_reasons=list(dict.fromkeys(reasons)),
    )


def without_coding(
    invoice: NormalisedInvoice,
    context: ResolvedContext,
    reasons: tuple[str, ...],
    alternatives: tuple[Candidate, ...] = (),
    index: ReferenceIndex | None = None,
    knowledge: KnowledgeBase | None = None,
) -> CodingProposal:
    """A proposal without lines, for the accountant to enter by hand: a credit note, or an
    invoice that nothing fits."""
    decision = Decision(rule="none", lines=(), alternatives=alternatives, reasons=reasons)
    shown = (
        _alternatives(decision, invoice, context, index, knowledge)
        if index is not None and knowledge is not None
        else []
    )
    return CodingProposal(
        invoice_id=invoice.document.id,
        bundle_id=context.bundle_id,
        document=DocumentRef(
            series=context.series,
            number=context.document_number,
            booking_date=context.booking_date,
        ),
        supplier=_supplier(invoice, context),
        invoice=_summary(invoice),
        confidence=Confidence(overall=0.0),
        evidence=_unique(_header_evidence(invoice, context)),
        alternatives=shown,
        validation=Validation(ok=True),
        needs_review=True,
        review_reasons=list(dict.fromkeys([*reasons, *_header_reasons(invoice, context)])),
    )


def _field_confidence(
    invoice: NormalisedInvoice,
    context: ResolvedContext,
    candidates: CandidateSet,
    decision: Decision,
    derivation: Derivation,
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
) -> dict[str, float]:
    by_precedent = decision.rule == "precedent"
    grant_sources = frozenset(t.zdroj for t in index.bundle.transfers)
    zdroj, analytika = [], []
    for line in decision.lines:
        position = index.expense[line.candidate.budget_key]
        if by_precedent:
            zdroj.append(0.99)
        elif position.zdroj == context.zdroj:
            zdroj.append(0.95)
        else:
            expected = knowledge.expects_transfer(position.zdroj, grant_sources)
            zdroj.append(0.8 if expected else 0.6)
        tier = line.candidate.tier
        if by_precedent:
            analytika.append(0.95)
        else:
            analytika.append(
                0.9
                if tier >= 2
                else 0.85
                if tier == 1
                else 0.8
                if position.analytika == "000"
                else 0.6
            )
    ocr = invoice.document.ocr_meta.confidence
    return {
        "ek": min(line.confidence for line in decision.lines),
        "cofog": 0.95 if by_precedent else 0.9 if candidates.function_explicit else 0.85,
        "zdroj": min(zdroj),
        "analytika": min(analytika),
        "md": derivation.md_confidence,
        "dal": derivation.dal_confidence,
        "booking_date": 0.0 if context.booking_date is None else ocr.get("handwritten.date", 1.0),
        "document_number": (
            0.5 if context.number_source == "counter" else ocr.get("handwritten.number", 1.0)
        ),
    }


def _header_reasons(invoice: NormalisedInvoice, context: ResolvedContext) -> list[str]:
    return [
        *invoice.issues,
        *context.issues,
        *(f"the OCR is unsure of {path}" for path in invoice.low_confidence),
    ]


def _header_evidence(invoice: NormalisedInvoice, context: ResolvedContext) -> list[Evidence]:
    evidence = []
    if context.booking_date is not None:
        d = context.booking_date
        detail = f"{d.day}.{d.month}.{d.year % 100:02d} written on the scan"
        evidence.append(Evidence(field="booking_date", source="handwritten", detail=detail))
    if context.number_source == "handwritten":
        detail = f"{invoice.handwritten_number} written on the scan"
        evidence.append(Evidence(field="document_number", source="handwritten", detail=detail))
    else:
        detail = f"no handwritten number read; {context.document_number} is next in the counter"
        evidence.append(Evidence(field="document_number", source="counter", detail=detail))
    return evidence


def _alternatives(
    decision: Decision,
    invoice: NormalisedInvoice,
    context: ResolvedContext,
    index: ReferenceIndex | None,
    knowledge: KnowledgeBase | None,
) -> list[Alternative]:
    if index is None or knowledge is None:
        return []
    chosen = {line.candidate.budget_key for line in decision.lines}
    shown = []
    for candidate in decision.alternatives:
        if candidate.budget_key in chosen:
            continue
        position = index.expense[candidate.budget_key]
        md, _, _ = debit_account(position, candidate, invoice, context, index, knowledge)
        why = candidate.evidence[0].detail if candidate.evidence else ", ".join(candidate.sources)
        shown.append(
            Alternative(
                budget_key=candidate.budget_key,
                md=md,
                score=round(min(candidate.score, 1.0), 2),
                why=why,
            )
        )
    return shown


def _supplier(invoice: NormalisedInvoice, context: ResolvedContext) -> SupplierRef:
    return SupplierRef(
        name=invoice.document.supplier.name,
        ico=invoice.supplier_ico,
        known=context.supplier is not None,
    )


def _summary(invoice: NormalisedInvoice) -> InvoiceSummary:
    header = invoice.document.invoice
    vat = invoice.document.totals.vat
    return InvoiceSummary(
        number=header.number,
        issued=header.issue_date,
        delivered=header.delivery_date,
        due=header.due_date,
        vs=header.variable_symbol,
        gross=invoice.gross,
        vat=vat.quantize(Decimal("0.01")) if vat is not None else None,
    )


def _unique(evidence: list[Evidence]) -> list[Evidence]:
    return list({(e.field, e.source, e.detail): e for e in evidence}.values())
