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
from riso.engine.s7_explain import explain, manual_entry
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
    invoice = normalise(document)
    context = resolve(invoice, entity=entity, bundle=bundle, memory=memory, counters=counters)
    if invoice.is_credit_note:
        return manual_entry(invoice, context, CREDIT_NOTE_REASON)
    index = ReferenceIndex(bundle)
    candidates = generate_candidates(invoice, context, index, knowledge)
    decision = decide(invoice, context, candidates)
    coding = derive_coding(invoice, context, decision, index, knowledge)
    validation = validate(invoice, context, coding, index)
    return explain(invoice, context, decision, coding, validation)
