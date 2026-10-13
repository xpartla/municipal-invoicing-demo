"""S3, candidate generation. Three generators, merged with their provenance:

- supplier precedent: how this supplier's earlier invoices were coded;
- lexicon and rules: concepts found in the text propose economic codes, and the function
  map, the expected zdroj and the descriptions narrow them to budget positions;
- similarity: budget positions whose description shares words with the invoice.

An entry that names its own building or activity gets candidates of its own, for the
per-entry split in S4."""

from collections.abc import Iterable
from dataclasses import dataclass

from riso.contracts import BudgetPosition, Evidence, budget_key
from riso.engine.models import Candidate, CandidateSet, Hit, NormalisedInvoice, ResolvedContext
from riso.knowledge import STRONG, KnowledgeBase
from riso.reference import ReferenceIndex
from riso.text import coverage, stems, words

PRECEDENT_SCORE = 0.95
RULE_SCORE = 0.8
CANTEEN_SCORE = 0.9
SIMILARITY_SCORE = 0.5
AGREEMENT_BONUS = 0.03
MAX_SCORE = 0.98
SIMILAR = 0.6  # share of a description's words found in the invoice that counts as naming it
FULL = 1.0  # every word of the description: the invoice names the position itself
SIMILARITY_FLOOR = 0.5
SIMILARITY_KEEP = 10


@dataclass(frozen=True)
class _EkOption:
    """An economic code worth searching, and why."""

    ek: str
    weight: float
    rank: int
    evidence: Evidence
    consistent: bool = True  # False: a supplier habit the invoice's concepts contradict


@dataclass(frozen=True)
class _Focus:
    """What candidates are measured against: the whole invoice or one entry."""

    function: str
    explicit: bool
    concepts: frozenset[str]
    concept_eks: frozenset[str]  # what the strong concepts propose
    named_functions: frozenset[str]  # every building or activity the invoice names
    stems: frozenset[str]
    grant: bool


@dataclass(frozen=True)
class _Fit:
    function_factor: float
    zdroj_factor: float
    analytika_factor: float
    tier: int
    consistent: bool
    evidence: tuple[Evidence, ...]


def generate_candidates(
    invoice: NormalisedInvoice,
    context: ResolvedContext,
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
) -> CandidateSet:
    function, explicit, function_evidence = _invoice_function(invoice, context, knowledge)
    concepts = _strong(invoice.concept_names(), knowledge)
    focus = _Focus(
        function=function,
        explicit=explicit,
        concepts=concepts,
        concept_eks=_concept_eks(concepts, knowledge),
        named_functions=frozenset(invoice.named_functions()),
        stems=stems(invoice.all_words(), knowledge.stopwords),
        grant="grant" in invoice.concept_names(),
    )
    options = _concept_options(invoice.concepts, knowledge)
    options += _precedent_options(context, focus.concept_eks)
    found = _precedent_candidates(context, index)
    found += _rule_candidates(options, focus, context, index, knowledge)
    if context.canteen_food:
        found += _canteen_candidates(index, knowledge)
    found += _similarity_candidates(focus, context, index, knowledge)
    return CandidateSet(
        invoice=_merge(found),
        lines=tuple(
            _line_candidates(i, invoice, context, index, knowledge, focus)
            for i in range(len(invoice.document.lines))
        ),
        function=function,
        function_explicit=explicit,
        function_evidence=function_evidence,
    )


def position_function(position: BudgetPosition) -> str:
    return f"{position.oddiel} {position.trieda}"


def canteen_key(knowledge: KnowledgeBase, analytika: str | None = None) -> str:
    rule = knowledge.canteen
    oddiel, trieda = rule.function.split()
    return budget_key(rule.ek, rule.zdroj, oddiel, trieda, analytika or rule.analytika)


def _invoice_function(
    invoice: NormalisedInvoice, context: ResolvedContext, knowledge: KnowledgeBase
) -> tuple[str, bool, Evidence]:
    if context.canteen:
        function = knowledge.canteen.function
        return function, True, Evidence(field="cofog", source="rule", detail=f"canteen, {function}")
    named = invoice.invoice_functions()
    if named:
        hit = next(h for h in invoice.functions if h.meaning == named[0])
        detail = f"'{hit.term}' in {hit.source} names {named[0]}"
        if len(named) > 1:
            detail += f"; also named: {', '.join(named[1:])}"
        return named[0], True, Evidence(field="cofog", source="lexicon", detail=detail)
    default = knowledge.functions.default
    name = next(f.name for f in knowledge.functions.functions if f.function == default)
    detail = f"no building or activity named, default {name} {default}"
    return default, False, Evidence(field="cofog", source="rule", detail=detail)


def _strong(concepts: Iterable[str], knowledge: KnowledgeBase) -> frozenset[str]:
    return frozenset(c for c in concepts if knowledge.lexicon.concepts[c].weight >= STRONG)


def _concept_eks(concepts: Iterable[str], knowledge: KnowledgeBase) -> frozenset[str]:
    return frozenset(ek for name in concepts for ek in knowledge.lexicon.concepts[name].ek)


def _concept_options(hits: Iterable[Hit], knowledge: KnowledgeBase) -> list[_EkOption]:
    first: dict[str, Hit] = {}
    for hit in hits:
        first.setdefault(hit.meaning, hit)
    return [
        _EkOption(
            ek=ek,
            weight=knowledge.lexicon.concepts[name].weight,
            rank=rank,
            evidence=Evidence(
                field="ek",
                source="lexicon",
                detail=f"'{hit.term}' in {hit.source} suggests EK {ek}",
            ),
        )
        for name, hit in first.items()
        for rank, ek in enumerate(knowledge.lexicon.concepts[name].ek)
    ]


def _precedent_options(context: ResolvedContext, concept_eks: frozenset[str]) -> list[_EkOption]:
    """This supplier's usual economic codes, searched under the invoice's own function. Where
    the invoice's strong concepts propose other codes, they stay alternatives: a road
    builder's repairs say nothing about its construction invoice."""
    if context.supplier is None:
        return []
    eks = dict.fromkeys(
        line.budget_key.split(" ")[0] for p in context.supplier.precedents for line in p.lines
    )
    return [
        _EkOption(
            ek=ek,
            weight=1.0,
            rank=0,
            evidence=Evidence(
                field="ek",
                source="supplier_memory",
                detail=f"this supplier's earlier invoices used EK {ek}",
            ),
            consistent=not concept_eks or ek in concept_eks,
        )
        for ek in eks
    ]


def _precedent_candidates(
    context: ResolvedContext, index: ReferenceIndex, function: str | None = None
) -> list[Candidate]:
    if context.supplier is None:
        return []
    found = []
    for rank, precedent in enumerate(context.supplier.precedents):
        for line in precedent.lines:
            position = index.expense.get(line.budget_key)
            if position is None or function not in (None, position_function(position)):
                continue
            label = precedent.document_number or "an earlier invoice"
            found.append(
                Candidate(
                    budget_key=line.budget_key,
                    score=PRECEDENT_SCORE - 0.02 * rank,
                    sources=("supplier_memory",),
                    evidence=(
                        Evidence(
                            field="ek",
                            source="supplier_memory",
                            detail=f"{label} coded {line.budget_key} for this IČO",
                        ),
                    ),
                    precedent=line,
                    precedent_number=precedent.document_number,
                    precedent_rank=rank,
                )
            )
    return found


def _rule_candidates(
    options: list[_EkOption],
    focus: _Focus,
    context: ResolvedContext,
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
) -> list[Candidate]:
    best: dict[str, _EkOption] = {}
    for option in options:
        kept = best.get(option.ek)
        if kept is None or (option.weight, -option.rank) > (kept.weight, -kept.rank):
            best[option.ek] = option
    found = []
    for option in best.values():
        if knowledge.su_for(option.ek) is None:
            continue
        for position in index.expense_by_ek.get(option.ek, ()):
            fit = _fit(position, focus, context, index, knowledge)
            score = (
                RULE_SCORE
                * option.weight
                * (1 - 0.08 * option.rank)
                * fit.function_factor
                * fit.zdroj_factor
                * fit.analytika_factor
            )
            found.append(
                Candidate(
                    budget_key=position.key,
                    score=round(min(0.95, score), 3),
                    sources=(option.evidence.source,),
                    evidence=(option.evidence, *fit.evidence),
                    consistent=fit.consistent and option.weight >= STRONG and option.consistent,
                    tier=fit.tier,
                )
            )
    return found


def _canteen_candidates(index: ReferenceIndex, knowledge: KnowledgeBase) -> list[Candidate]:
    """The canteen food rule fixes the position; its alternative analytics stay as options."""
    rule = knowledge.canteen
    found = []
    for i, analytika in enumerate([rule.analytika, *rule.alternatives]):
        key = canteen_key(knowledge, analytika)
        if key not in index.expense:
            continue
        detail = (
            f"canteen food rule: {key}"
            if i == 0
            else f"canteen food, alternative analytika {analytika}"
        )
        found.append(
            Candidate(
                budget_key=key,
                score=CANTEEN_SCORE if i == 0 else 0.6,
                sources=("rule",),
                evidence=(Evidence(field="ek", source="rule", detail=detail),),
                consistent=i == 0,
                tier=1,
            )
        )
    return found


def _similarity_candidates(
    focus: _Focus, context: ResolvedContext, index: ReferenceIndex, knowledge: KnowledgeBase
) -> list[Candidate]:
    found = []
    for position in index.bundle.budget_positions_expense:
        if knowledge.su_for(position.ek) is None:
            continue
        similarity = coverage(stems(_description_words(position), knowledge.stopwords), focus.stems)
        if similarity < SIMILARITY_FLOOR:
            continue
        fit = _fit(position, focus, context, index, knowledge)
        score = (
            SIMILARITY_SCORE
            * similarity
            * fit.function_factor
            * fit.zdroj_factor
            * fit.analytika_factor
        )
        found.append(
            Candidate(
                budget_key=position.key,
                score=round(score, 3),
                sources=("similarity",),
                evidence=(
                    Evidence(
                        field="ek",
                        source="similarity",
                        detail=f"'{position.description}' shares words with the invoice",
                    ),
                    *fit.evidence,
                ),
                # Words alone do not outvote the concepts: "odvod ... dane" in an insurance
                # invoice's small print does not make it a tax.
                consistent=fit.consistent
                and fit.tier >= 2
                and (not focus.concept_eks or position.ek in focus.concept_eks),
                tier=fit.tier,
            )
        )
    return sorted(found, key=lambda c: -c.score)[:SIMILARITY_KEEP]


def _line_candidates(
    i: int,
    invoice: NormalisedInvoice,
    context: ResolvedContext,
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
    invoice_focus: _Focus,
) -> tuple[Candidate, ...]:
    """Candidates for one entry, when it names its own building or activity. Entries that
    only name another kind of purchase stay on the invoice's line (decision 12)."""
    source = f"lines[{i}].description"
    functions = invoice.named_functions(source)
    if not functions:
        return ()
    concepts = _strong(invoice.concept_names(source), knowledge) or invoice_focus.concepts
    line_words = next(t.words for t in invoice.texts if t.source == source)
    focus = _Focus(
        function=functions[0],
        explicit=True,
        concepts=concepts,
        concept_eks=_concept_eks(concepts, knowledge),
        named_functions=invoice_focus.named_functions,
        stems=stems(line_words, knowledge.stopwords),
        grant=invoice_focus.grant,
    )
    hits = [h for h in invoice.concepts if h.source == source and h.meaning in concepts]
    if not hits:
        hits = [h for h in invoice.concepts if h.meaning in invoice_focus.concepts]
    options = _concept_options(hits, knowledge) + _precedent_options(context, focus.concept_eks)
    found = _precedent_candidates(context, index, focus.function)
    found += _rule_candidates(options, focus, context, index, knowledge)
    return _merge(found)


def _fit(
    position: BudgetPosition,
    focus: _Focus,
    context: ResolvedContext,
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
) -> _Fit:
    """How well a position fits: its function, its zdroj, and whether the invoice names its
    whole description (tier 3), names what it names (tier 2: most of its words and at least
    two of them), is about the same concept (tier 1), or neither. A position the invoice
    names in full fits whatever building the text mentions: the construction of the road to
    Szilvášok is budgeted under the office, not under roads. Naming in full includes the
    buildings the description names, so 'MŠ - elekt.energia' is not named by the office's
    electricity invoice."""
    description = _description_words(position)
    description_stems = stems(description, knowledge.stopwords)
    named = coverage(description_stems, focus.stems)
    enough = len(description_stems & focus.stems) >= 2
    shared = knowledge.concepts_in(description) & focus.concepts
    buildings = knowledge.functions_in(" ".join([position.description or "", *position.aliases]))
    if enough and named >= FULL and buildings <= focus.named_functions:
        tier = 3
    elif enough and named >= SIMILAR:
        tier = 2
    else:
        tier = 1 if shared else 0
    evidence: tuple[Evidence, ...] = ()
    if tier == 3:
        detail = f"the invoice names '{position.description}'"
        evidence = (Evidence(field="analytika", source="similarity", detail=detail),)
    elif tier == 2:
        detail = f"'{position.description}' names what the invoice names"
        evidence = (Evidence(field="analytika", source="similarity", detail=detail),)
    elif tier == 1:
        detail = f"'{position.description}' is about {', '.join(sorted(shared))}"
        evidence = (Evidence(field="analytika", source="lexicon", detail=detail),)

    function_ok = position_function(position) == focus.function
    zdroj_ok, zdroj_factor = _zdroj_fit(position, focus, context, index, knowledge)
    generic = position.analytika == "000" or _only_analytika(position, index)
    return _Fit(
        function_factor=1.0 if function_ok or tier == 3 else 0.55 if focus.explicit else 0.85,
        zdroj_factor=zdroj_factor,
        analytika_factor=1.15 if tier >= 2 else 1.1 if tier == 1 else 1.0 if generic else 0.8,
        tier=tier,
        consistent=(function_ok or tier == 3 or (tier == 2 and not focus.explicit))
        and zdroj_ok
        and (tier > 0 or generic),
        evidence=evidence,
    )


def _zdroj_fit(
    position: BudgetPosition,
    focus: _Focus,
    context: ResolvedContext,
    index: ReferenceIndex,
    knowledge: KnowledgeBase,
) -> tuple[bool, float]:
    """Own funds are expected, unless the invoice speaks of a grant; then a grant source.
    Where the budget funds an economic code and function only from another source, as the
    kindergarten's energy from the state's transfer, that source is the expected one."""
    zdroj = position.zdroj
    grant_source = knowledge.expects_transfer(
        zdroj, frozenset(t.zdroj for t in index.bundle.transfers)
    )
    if focus.grant:
        if grant_source:
            return True, 1.0
        return False, 0.85 if zdroj == context.zdroj else 0.5
    if zdroj == context.zdroj or not _has_zdroj(position, context.zdroj, index):
        return True, 1.0
    return False, 0.5


def _has_zdroj(position: BudgetPosition, zdroj: str, index: ReferenceIndex) -> bool:
    """The budget has the position's economic code and function from this source."""
    return any(
        other.zdroj == zdroj and position_function(other) == position_function(position)
        for other in index.expense_by_ek.get(position.ek, ())
    )


def _only_analytika(position: BudgetPosition, index: ReferenceIndex) -> bool:
    """No other analytika exists for the position's EK, zdroj and function."""
    return not any(
        other.key != position.key
        and other.zdroj == position.zdroj
        and position_function(other) == position_function(position)
        for other in index.expense_by_ek.get(position.ek, ())
    )


def _description_words(position: BudgetPosition) -> tuple[str, ...]:
    return words(" ".join([position.description or "", *position.aliases]))


def _merge(found: list[Candidate]) -> tuple[Candidate, ...]:
    """One candidate per position: the best score, a bonus when generators agree, and all
    the evidence."""
    groups: dict[str, list[Candidate]] = {}
    for candidate in found:
        groups.setdefault(candidate.budget_key, []).append(candidate)
    merged = []
    for key, group in groups.items():
        best = max(group, key=lambda c: c.score)
        sources = tuple(dict.fromkeys(s for c in group for s in c.sources))
        evidence = {(e.field, e.source, e.detail): e for c in group for e in c.evidence}
        with_precedent = min(
            (c for c in group if c.precedent is not None),
            key=lambda c: c.precedent_rank or 0,
            default=None,
        )
        merged.append(
            Candidate(
                budget_key=key,
                score=round(min(MAX_SCORE, best.score + AGREEMENT_BONUS * (len(sources) - 1)), 3),
                sources=sources,
                evidence=tuple(evidence.values()),
                consistent=any(c.consistent for c in group),
                tier=max(c.tier for c in group),
                precedent=with_precedent.precedent if with_precedent else None,
                precedent_number=with_precedent.precedent_number if with_precedent else None,
                precedent_rank=with_precedent.precedent_rank if with_precedent else None,
            )
        )
    return tuple(sorted(merged, key=lambda c: (-c.score, c.budget_key)))
