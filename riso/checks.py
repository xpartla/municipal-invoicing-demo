"""Consistency of the committed data with the dictionaries, the M0 exit criterion: every
entity's settings, seeded supplier memory and counters, and every dataset case's expected
coding resolve against the reference bundle. Run by `riso check` and by the tests."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from riso import paths
from riso.contracts import Counters, DatasetCase, EntityContext, SupplierMemory
from riso.contracts.schemas import stale_schemas
from riso.dataset import TAGS, load_cases
from riso.engine.s1_normalise import ico_is_valid
from riso.engine.s3_candidates import canteen_key
from riso.engine.s6_validate import SUPPLIER_SU, check_codes, check_coding
from riso.knowledge import KnowledgeBase, UnknownKnowledge, load_knowledge
from riso.reference import LocalReferenceSource, ReferenceIndex, UnknownEntity, parse_number
from riso.store import COUNTERS_FILE, MEMORY_FILE


@dataclass(frozen=True)
class CheckResult:
    name: str
    errors: list[str]


def run_checks(
    source: LocalReferenceSource | None = None,
    invoices_dir: Path = paths.INVOICES_DIR,
    initial_dir: Path = paths.INITIAL_STATE_DIR,
    schemas_dir: Path = paths.SCHEMAS_DIR,
) -> list[CheckResult]:
    source = source or LocalReferenceSource()
    stale = stale_schemas(schemas_dir)
    results = [
        CheckResult(
            "schemas match the contracts",
            [f"{name} is stale; run `riso export-schemas`" for name in stale],
        )
    ]
    for ico in source.entities():
        index = ReferenceIndex(source.bundle(ico))
        context = source.context(ico)
        memory = SupplierMemory.model_validate_json((initial_dir / ico / MEMORY_FILE).read_bytes())
        counters = Counters.model_validate_json((initial_dir / ico / COUNTERS_FILE).read_bytes())
        try:
            knowledge_found = knowledge_errors(load_knowledge(context.budget_year), index)
        except UnknownKnowledge as exc:
            knowledge_found = [str(exc)]
        results += [
            CheckResult(f"{ico} entity settings", context_errors(context, index)),
            CheckResult(f"{ico} supplier memory", memory_errors(memory, index)),
            CheckResult(f"{ico} counters", counter_errors(counters, index)),
            CheckResult(f"{ico} knowledge base {context.budget_year}", knowledge_found),
        ]
    cases = load_cases(invoices_dir)
    for case in cases:
        results.append(CheckResult(f"case {case.id}", case_errors(case, source)))
    used = {
        ico: Counters.model_validate_json((initial_dir / ico / COUNTERS_FILE).read_bytes())
        for ico in source.entities()
    }
    results.append(CheckResult("dataset as a whole", dataset_errors(cases, used)))
    return results


def context_errors(context: EntityContext, index: ReferenceIndex) -> list[str]:
    bundle = index.bundle
    errors = []
    if context.ico != bundle.entity.ico:
        errors.append(f"IČO {context.ico} differs from the bundle's {bundle.entity.ico}")
    if context.reference_period != bundle.period:
        errors.append(f"period {context.reference_period} differs from the bundle's")
    for series in (context.default_series, context.canteen_series):
        if series not in index.series:
            errors.append(f"series {series} is not among the document series")
    for dal in (context.default_dal, context.canteen_dal):
        if dal not in index.accounts or not dal.startswith(SUPPLIER_SU):
            errors.append(f"DAL {dal} is not a supplier account in the chart")
    return errors


def memory_errors(memory: SupplierMemory, index: ReferenceIndex) -> list[str]:
    errors = []
    for supplier in memory.suppliers:
        for precedent in supplier.precedents:
            label = f"{supplier.name} {precedent.document_number or ''}".strip()
            errors += _number_errors(precedent.document_number, index, label)
            for line in precedent.lines:
                errors += [
                    f"{label}: {e}" for e in check_codes(line.md, line.dal, line.budget_key, index)
                ]
    return errors


def counter_errors(counters: Counters, index: ReferenceIndex) -> list[str]:
    errors = [
        f"counter {key}: series {key.split('/')[0]} is not among the document series"
        for key in counters.last_used
        if key.split("/")[0] not in index.series
    ]
    for number in counters.used_numbers:
        errors += _number_errors(number, index, "used number")
    return errors


def knowledge_errors(knowledge: KnowledgeBase, index: ReferenceIndex) -> list[str]:
    """Accounts and positions the knowledge base names must exist in the entity's
    dictionaries. Economic codes and functions it names may be missing: the knowledge base
    serves a budget year, not one municipality."""
    errors = [
        f"bridge: SU {rule.su} for EK {rule.ek} is not in the chart of accounts"
        for rule in knowledge.bridge
        if rule.su not in index.accounts_by_su
    ]
    for side, table in (("debit", knowledge.au_rules.debit), ("credit", knowledge.au_rules.credit)):
        for su, rules in table.items():
            for au in dict.fromkeys([rules.default, *(rule.au for rule in rules.rules)]):
                if f"{su} {au}" not in index.accounts:
                    errors.append(f"AU rules: {side} account {su} {au} is not in the chart")
    canteen = knowledge.canteen
    for analytika in [canteen.analytika, *canteen.alternatives]:
        if (key := canteen_key(knowledge, analytika)) not in index.expense:
            errors.append(f"canteen rule: {key} is not in the approved budget")
    if canteen.md not in index.accounts:
        errors.append(f"canteen rule: MD {canteen.md} is not in the chart of accounts")
    return errors


def case_errors(case: DatasetCase, source: LocalReferenceSource) -> list[str]:
    invoice = case.invoice
    ico = "".join((invoice.customer.ico or "").split())
    try:
        index = ReferenceIndex(source.bundle(ico))
    except UnknownEntity:
        return [f"no reference data for the customer IČO {invoice.customer.ico!r}"]
    errors = [f"unknown tag {tag!r}" for tag in case.tags if tag not in TAGS]
    coding = case.expected.coding
    if coding is None:
        return errors
    errors += check_coding(coding, index, gross=_expected_gross(case)).errors
    document = coding.document
    if document.booking_date != invoice.handwritten.date:
        errors.append(
            f"booking date {document.booking_date} is not the handwritten date "
            f"{invoice.handwritten.date}"
        )
    written = invoice.handwritten.number
    series = index.series.get(document.series)
    if written is not None and not written.isdigit():
        errors.append(f"handwritten number {written!r} is not a number")
    elif written is not None and series is not None and document.number is not None:
        parsed = parse_number(series.pattern, document.number)
        if parsed is not None and parsed.sequence != int(written):
            errors.append(f"number {document.number} is not the handwritten {written}")
    return errors


def dataset_errors(cases: list[DatasetCase], counters: dict[str, Counters]) -> list[str]:
    """What holds across cases: every document number is taken once and not by the initial
    state; the seed cases are booked before the held-out ones, which never feed supplier
    memory; synthetic cases say so; supplier IČOs pass the check digit except where a case
    was built with OCR noise."""
    errors = []
    taken: dict[tuple[str, str], str] = {}
    for case in cases:
        coding = case.expected.coding
        ico = "".join((case.invoice.customer.ico or "").split())
        number = coding.document.number if coding else None
        if number is not None:
            if (ico, number) in taken:
                errors.append(f"{case.id}: number {number} is also taken by {taken[ico, number]}")
            elif ico in counters and number in counters[ico].used_numbers:
                errors.append(f"{case.id}: number {number} is already used in the initial state")
            taken[ico, number] = case.id
        if case.split != "anchor" and not case.invoice.ocr_meta.synthetic:
            errors.append(f"{case.id}: a {case.split} case must be flagged ocr_meta.synthetic")
        supplier_ico = "".join((case.invoice.supplier.ico or "").split())
        if "ocr-noise" not in case.tags and not (
            len(supplier_ico) == 8 and supplier_ico.isdigit() and ico_is_valid(supplier_ico)
        ):
            errors.append(f"{case.id}: supplier IČO {case.invoice.supplier.ico!r} is not valid")
    seed = [c.invoice.handwritten.date for c in cases if c.split == "seed"]
    heldout = [c.invoice.handwritten.date for c in cases if c.split == "heldout"]
    seed_dates = [d for d in seed if d is not None]
    heldout_dates = [d for d in heldout if d is not None]
    if seed_dates and heldout_dates and max(seed_dates) >= min(heldout_dates):
        errors.append(
            f"seed cases run until {max(seed_dates)}, held-out cases start on "
            f"{min(heldout_dates)}; the held-out set must come later"
        )
    return errors


def _expected_gross(case: DatasetCase) -> Decimal | None:
    """What the coding must add up to: the invoice total, or, when the case was built with
    an unreadable or mistyped total, the sum of its entries rounded to cents."""
    invoice = case.invoice
    entries = [line.gross for line in invoice.lines]
    if "ocr-noise" in case.tags and entries and None not in entries:
        return sum(entries, Decimal(0)).quantize(Decimal("0.01"))
    return invoice.totals.gross


def _number_errors(number: str | None, index: ReferenceIndex, label: str) -> list[str]:
    if number is None:
        return []
    series = index.series.get(number.split("/")[0])
    if series is None or parse_number(series.pattern, number) is None:
        return [f"{label}: {number} does not follow any document series pattern"]
    return []
