"""S5, posting derivation: EK to SU through the bridge, AU by the rules or the precedent, the
supplier account by series and project, the transfer for grant sources, amounts, and
descriptions in the accountant's short style. Returns the complete coding: the header from
S2, the budget lines chosen in S4 and one posting line for each."""

import re

from riso.contracts import BudgetLine, BudgetPosition, Coding, DocumentRef, Evidence, PostingLine
from riso.engine.models import (
    Candidate,
    Decision,
    Derivation,
    NormalisedInvoice,
    ResolvedContext,
)
from riso.engine.s3_candidates import position_function
from riso.knowledge import KnowledgeBase
from riso.knowledge.model import AccountRules, AuRule
from riso.reference import ReferenceIndex
from riso.text import coverage, stems, words

_MONTH_OF_SERVICE = re.compile(r"\b(1[0-2]|0?[1-9])/(20\d\d)\b")


def derive_coding(
    invoice: NormalisedInvoice,
    context: ResolvedContext,
    decision: Decision,
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
) -> Derivation:
    posting, budget, evidence = [], [], []
    md_confidence = dal_confidence = 1.0
    for chosen in decision.lines:
        position = index.expense[chosen.candidate.budget_key]
        md, md_score, md_evidence = debit_account(
            position, chosen.candidate, invoice, context, index, knowledge
        )
        dal, dal_score, dal_evidence = credit_account(
            position, chosen.candidate, context, index, knowledge
        )
        transfer, transfer_evidence = choose_transfer(position, invoice, index, knowledge)
        budget_text, posting_text = line_texts(position, chosen.candidate, invoice, knowledge)
        budget.append(
            BudgetLine(
                key=position.key,
                ek=position.ek,
                zdroj=position.zdroj,
                oddiel=position.oddiel,
                trieda=position.trieda,
                analytika=position.analytika,
                amount=chosen.amount,
                text=budget_text,
                transfer=transfer,
            )
        )
        posting.append(
            PostingLine(md=md, dal=dal, amount=chosen.amount, text=posting_text, transfer=transfer)
        )
        evidence += [md_evidence, dal_evidence, *transfer_evidence]
        md_confidence, dal_confidence = min(md_confidence, md_score), min(dal_confidence, dal_score)
    document = DocumentRef(
        series=context.series, number=context.document_number, booking_date=context.booking_date
    )
    return Derivation(
        coding=Coding(document=document, posting=posting, budget=budget),
        evidence=tuple(evidence),
        md_confidence=md_confidence,
        dal_confidence=dal_confidence,
    )


def debit_account(
    position: BudgetPosition,
    candidate: Candidate | None,
    invoice: NormalisedInvoice,
    context: ResolvedContext,
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
) -> tuple[str, float, Evidence]:
    """The MD account: the precedent's, the canteen rule's, or the bridge's SU with the AU the
    rules choose."""
    precedent = candidate.precedent if candidate else None
    if precedent is not None and precedent.budget_key == position.key:
        label = candidate.precedent_number if candidate else None
        detail = f"{label or 'an earlier invoice'} debited {precedent.md}"
        return precedent.md, 0.97, Evidence(field="md", source="supplier_memory", detail=detail)
    canteen = knowledge.canteen
    if context.canteen_food and position.ek == canteen.ek:
        detail = f"canteen food rule: {canteen.md}"
        return canteen.md, 0.9, Evidence(field="md", source="rule", detail=detail)

    rule = knowledge.su_for(position.ek)
    if rule is None:
        raise ValueError(f"no bridge rule for EK {position.ek}; S3 should not propose it")
    au, reason = _analytic(
        knowledge.au_rules.debit.get(rule.su),
        concepts=invoice.concept_names(),
        function=position_function(position),
        ek=position.ek,
        zdroj=position.zdroj,
        words=invoice.all_words() + words(position.description or ""),
    )
    key = f"{rule.su} {au}"
    if key not in index.accounts:
        key = (
            f"{rule.su} 000"
            if f"{rule.su} 000" in index.accounts
            else index.accounts_by_su[rule.su][0].key
        )
    variants = len(index.accounts_by_su[rule.su])
    confidence = 0.85 if reason != "default" or variants == 1 else 0.75
    detail = f"EK {position.ek} is booked to {rule.su} ({rule.note}); AU {key[4:]}: {reason}"
    return key, confidence, Evidence(field="md", source="rule", detail=detail)


def credit_account(
    position: BudgetPosition,
    candidate: Candidate | None,
    context: ResolvedContext,
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
) -> tuple[str, float, Evidence]:
    """The DAL account: the precedent's, or the supplier account of the series, with the
    analytic account of a project where a rule names one."""
    precedent = candidate.precedent if candidate else None
    if precedent is not None and precedent.budget_key == position.key:
        detail = f"{candidate.precedent_number or 'an earlier invoice'} credited {precedent.dal}"
        return precedent.dal, 0.99, Evidence(field="dal", source="supplier_memory", detail=detail)
    entity = context.entity
    default = entity.canteen_dal if context.canteen else entity.default_dal
    su, au = default.split(" ")
    reason = f"the {context.series} series' supplier account"
    if not context.canteen:
        project_au, project = _analytic(
            knowledge.au_rules.credit.get(su),
            concepts=frozenset(),
            function=position_function(position),
            ek=position.ek,
            zdroj=position.zdroj,
            words=(),
        )
        if project != "default" and f"{su} {project_au}" in index.accounts:
            au, reason = project_au, project
    return f"{su} {au}", 0.99, Evidence(field="dal", source="rule", detail=f"{su} {au}: {reason}")


def choose_transfer(
    position: BudgetPosition,
    invoice: NormalisedInvoice,
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
) -> tuple[str | None, tuple[Evidence, ...]]:
    """The transfer a grant-funded line belongs to: the only one with its zdroj, or the one
    whose name the invoice and the position description share most words with."""
    grant_sources = frozenset(t.zdroj for t in index.bundle.transfers)
    if not knowledge.expects_transfer(position.zdroj, grant_sources):
        return None, ()
    options = index.transfers_by_zdroj.get(position.zdroj, [])
    if len(options) == 1:
        detail = f"the only transfer with zdroj {position.zdroj}: {options[0].name}"
        return options[0].id, (Evidence(field="transfer", source="rule", detail=detail),)
    target = stems(invoice.all_words() + words(position.description or ""), knowledge.stopwords)
    scored = []
    for transfer in options:
        name = stems(words(transfer.name), knowledge.stopwords)
        scored.append(((len(name & target), coverage(name, target)), transfer))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if scored and scored[0][0][1] >= 0.5 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        best = scored[0][1]
        detail = f"'{best.name}' shares the most words with the invoice"
        return best.id, (Evidence(field="transfer", source="similarity", detail=detail),)
    return None, ()


def line_texts(
    position: BudgetPosition,
    candidate: Candidate | None,
    invoice: NormalisedInvoice,
    knowledge: KnowledgeBase,
) -> tuple[str, str]:
    """Budget and posting text: the precedent's with this invoice's month of service, or the
    position's description and the concept's text in the accountant's short style."""
    precedent = candidate.precedent if candidate else None
    if precedent is not None and precedent.budget_key == position.key:
        posting = precedent.posting_text
        if invoice.service_period is not None:
            year, month = invoice.service_period
            posting = _MONTH_OF_SERVICE.sub(f"{month}/{year}", posting)
        return precedent.budget_text, posting
    limit = knowledge.style.max_length
    budget_text = _short(position.description or position.key, limit)
    concepts = invoice.concept_names()
    texts = [
        concept.text
        for name, concept in sorted(knowledge.lexicon.concepts.items(), key=lambda c: -c[1].weight)
        if name in concepts and concept.text and position.ek in concept.ek
    ]
    posting_text = texts[0] if texts else budget_text
    if invoice.service_period and concepts & set(knowledge.style.month_for):
        year, month = invoice.service_period
        posting_text = f"{posting_text} {month}/{year}"
    return budget_text, _short(posting_text, limit)


def _analytic(
    rules: AccountRules | None,
    *,
    concepts: frozenset[str],
    function: str,
    ek: str,
    zdroj: str,
    words: tuple[str, ...],
) -> tuple[str, str]:
    """The AU of the first rule whose conditions all hold, and why; else the default."""
    if rules is None:
        return "000", "default"
    for rule in rules.rules:
        if rule.concepts and not concepts & set(rule.concepts):
            continue
        if rule.function and function not in rule.function:
            continue
        if rule.ek and not any(ek.startswith(prefix) for prefix in rule.ek):
            continue
        if rule.zdroj and zdroj not in rule.zdroj:
            continue
        if rule.terms and not rule.term_index.search(words):
            continue
        return rule.au, rule.note or _describe(rule)
    return rules.default, "default"


def _describe(rule: AuRule) -> str:
    conditions = [
        f"{name} {', '.join(values)}"
        for name, values in (
            ("concept", rule.concepts),
            ("function", rule.function),
            ("EK", rule.ek),
            ("zdroj", rule.zdroj),
            ("term", rule.terms),
        )
        if values
    ]
    return "; ".join(conditions)


def _short(text: str, limit: int) -> str:
    """Lower-case start unless it is an abbreviation (MŠ, ŠJ), cut at a word boundary."""
    text = " ".join(text.split())
    if len(text) > 1 and not text[:2].isupper():
        text = text[0].lower() + text[1:]
    if len(text) <= limit:
        return text
    cut = text[: limit + 1].rsplit(" ", 1)[0]  # keeps a last word that ends at the limit
    return cut.rstrip(" ,-")
