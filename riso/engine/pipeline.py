"""The pipeline of plan section 5. Each stage is a pure function of its inputs; state such as
supplier memory and counters comes in as arguments and goes out through S8."""

from riso.contracts import (
    CodingProposal,
    Counters,
    EntityContext,
    InvoiceDocument,
    ReferenceBundle,
    SupplierMemory,
)
from riso.engine.s1_normalise import normalise
from riso.engine.s2_resolve import resolve
from riso.engine.s3_candidates import generate_candidates
from riso.engine.s4_decide import decide
from riso.engine.s5_posting import derive_coding
from riso.engine.s6_validate import validate
from riso.engine.s7_explain import explain, without_coding
from riso.knowledge import KnowledgeBase
from riso.reference import ReferenceIndex

CREDIT_NOTE_REASON = "credit note, manual entry"


def code_invoice(
    document: InvoiceDocument,
    *,
    entity: EntityContext,
    bundle: ReferenceBundle,
    memory: SupplierMemory,
    counters: Counters,
    knowledge: KnowledgeBase,
) -> CodingProposal:
    index = ReferenceIndex(bundle)
    invoice = normalise(document, knowledge)
    context = resolve(
        invoice, entity=entity, index=index, memory=memory, counters=counters, knowledge=knowledge
    )
    if invoice.is_credit_note:
        return without_coding(invoice, context, (CREDIT_NOTE_REASON,))
    candidates = generate_candidates(invoice, context, index, knowledge)
    decision = decide(invoice, context, candidates, index, knowledge)
    if not decision.lines:
        return without_coding(
            invoice, context, decision.reasons, decision.alternatives, index, knowledge
        )
    derivation = derive_coding(invoice, context, decision, index, knowledge)
    validation = validate(invoice, context, derivation.coding, index, knowledge)
    return explain(invoice, context, candidates, decision, derivation, validation, index, knowledge)
