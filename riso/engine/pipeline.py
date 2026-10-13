"""The pipeline of plan section 5. Each stage is a pure function of its inputs; state such as
supplier memory and counters comes in as arguments and goes out through S8."""

from riso.contracts import (
    Alternative,
    CodingProposal,
    Counters,
    EntityContext,
    InvoiceDocument,
    ReferenceBundle,
    SupplierMemory,
)
from riso.engine.models import Candidate, ResolvedContext
from riso.engine.s1_normalise import normalise
from riso.engine.s2_resolve import resolve
from riso.engine.s3_candidates import generate_candidates
from riso.engine.s4_decide import decide
from riso.engine.s5_posting import (
    choose_transfer,
    credit_account,
    debit_account,
    derive_coding,
    line_texts,
)
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


def code_line(
    document: InvoiceDocument,
    budget_key: str,
    *,
    entity: EntityContext,
    bundle: ReferenceBundle,
    memory: SupplierMemory,
    counters: Counters,
    knowledge: KnowledgeBase,
) -> Alternative:
    """The whole line a budget position brings for this invoice, for a position the
    accountant picks from the budget: MD, DAL, transfer and texts as S5 derives them, from
    the supplier's precedent with that position when there is one. Raises KeyError for a
    position that is not in the budget."""
    index = ReferenceIndex(bundle)
    position = index.expense[budget_key]
    invoice = normalise(document, knowledge)
    context = resolve(
        invoice, entity=entity, index=index, memory=memory, counters=counters, knowledge=knowledge
    )
    candidate = _precedent_for(context, budget_key)
    md = None
    if knowledge.su_for(position.ek) is not None:
        md, _, _ = debit_account(position, candidate, invoice, context, index, knowledge)
    dal, _, _ = credit_account(position, candidate, context, index, knowledge)
    transfer, _ = choose_transfer(position, invoice, index, knowledge)
    budget_text, posting_text = line_texts(position, candidate, invoice, knowledge)
    return Alternative(
        budget_key=budget_key,
        md=md,
        dal=dal,
        transfer=transfer,
        budget_text=budget_text,
        posting_text=posting_text,
        score=0.0,
        why="picked from the budget",
    )


def _precedent_for(context: ResolvedContext, budget_key: str) -> Candidate | None:
    """The supplier's newest precedent line with this position, as a candidate."""
    if context.supplier is None:
        return None
    for precedent in context.supplier.precedents:
        for line in precedent.lines:
            if line.budget_key == budget_key:
                return Candidate(
                    budget_key=budget_key,
                    score=1.0,
                    sources=("supplier_memory",),
                    evidence=(),
                    precedent=line,
                    precedent_number=precedent.document_number,
                )
    return None
