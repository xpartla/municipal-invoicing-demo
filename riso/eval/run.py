"""`evaluate`: codes one split of the dataset and reports the metrics of plan section 9.

Supplier memory starts from data/initial_state, never from the runtime state in var/, so a
demo cannot change the numbers. The anchor and seed cases feed it the way S8 does when the
accountant accepts a proposal: their expected coding becomes the supplier's precedent and
their number is used up. Held-out cases are coded against the memory of all anchor and seed
cases and never feed it ("frozen"). Anchor and seed cases are coded in booking-date order,
each with the memory of the cases booked before it ("online"), which is how memory grows in
use."""

import datetime as dt
import hashlib
from pathlib import Path

from riso import __version__, paths
from riso.contracts import (
    CaseResult,
    Counters,
    DatasetCase,
    EvalReport,
    SupplierMemory,
    Target,
)
from riso.contracts.eval import Split
from riso.dataset import TAGS, load_cases
from riso.engine import code_invoice
from riso.engine.s1_normalise import ico_is_valid
from riso.engine.s8_feedback import add_precedent, record_number
from riso.eval.metrics import by_supplier, by_tag, metrics, score_case
from riso.knowledge import load_knowledge
from riso.reference import LocalReferenceSource, ReferenceIndex
from riso.store import COUNTERS_FILE, MEMORY_FILE
from riso.text import fold

FEEDING_SPLITS = ("anchor", "seed")

# The demo targets of plan section 9: (metric, at least).
TARGETS = (("ek", 0.90), ("full_key", 0.85), ("validation", 1.0))


def evaluate(
    split: Split = "heldout",
    *,
    entity: str | None = None,
    invoices_dir: Path = paths.INVOICES_DIR,
    initial_dir: Path = paths.INITIAL_STATE_DIR,
    source: LocalReferenceSource | None = None,
) -> EvalReport:
    source = source or LocalReferenceSource()
    cases = load_cases(invoices_dir)
    ico = entity or _single_entity([c for c in cases if c.split == split], split)
    cases = [c for c in cases if _customer(c) == ico]
    context = source.context(ico)
    bundle = source.bundle(ico, context.reference_period)
    index = ReferenceIndex(bundle)
    knowledge = load_knowledge(context.budget_year)
    memory = SupplierMemory.model_validate_json((initial_dir / ico / MEMORY_FILE).read_bytes())
    counters = Counters.model_validate_json((initial_dir / ico / COUNTERS_FILE).read_bytes())

    def code(case: DatasetCase, memory: SupplierMemory, counters: Counters) -> CaseResult:
        proposal = code_invoice(
            case.invoice,
            entity=context,
            bundle=bundle,
            memory=memory,
            counters=counters,
            knowledge=knowledge,
        )
        return score_case(case, proposal, known=_known(case, memory))

    feeding = sorted((c for c in cases if c.split in FEEDING_SPLITS), key=_booked)
    results = []
    for case in feeding:
        if case.split == split:
            results.append(code(case, memory, counters))
        memory, counters = _feed(case, memory, counters, index)
    if split not in FEEDING_SPLITS:
        results = [code(case, memory, counters) for case in cases if case.split == split]

    found = metrics(results)
    return EvalReport(
        entity_ico=ico,
        split=split,
        memory="online" if split in FEEDING_SPLITS else "frozen",
        generated_at=dt.datetime.now(dt.UTC).replace(microsecond=0),
        engine_version=__version__,
        bundle_id=bundle.bundle_id,
        dataset_sha256=dataset_digest(invoices_dir / split),
        precedent_cases=sum(1 for c in feeding if c.expected.coding is not None),
        metrics=found,
        targets=[
            Target(
                metric=name,
                target=target,
                value=found[name].value,
                met=found[name].value is not None and found[name].value >= target,
            )
            for name, target in TARGETS
        ],
        by_supplier=by_supplier(results),
        by_tag=by_tag(results, TAGS),
        cases=results,
    )


def dataset_digest(directory: Path) -> str:
    """SHA-256 over the split's case files, names and contents, so a report names the exact
    ground truth it was measured against."""
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.json")):
        digest.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _feed(
    case: DatasetCase, memory: SupplierMemory, counters: Counters, index: ReferenceIndex
) -> tuple[SupplierMemory, Counters]:
    """The case's expected coding as if the accountant had accepted it (S8), kept newest
    first by booking date, since the engine ranks a supplier's precedents in that order."""
    coding = case.expected.coding
    if coding is None:
        return memory, counters
    supplier = case.invoice.supplier
    ico = _ico(supplier.ico)
    if ico is not None:
        memory = add_precedent(
            memory,
            ico=ico,
            name=supplier.name or ico,
            coding=coding,
            variable_symbol=case.invoice.invoice.variable_symbol,
        )
        memory = _newest_first(memory)
    return memory, record_number(coding.document.number, counters, index)


def _newest_first(memory: SupplierMemory) -> SupplierMemory:
    suppliers = [
        record.model_copy(
            update={
                "precedents": sorted(
                    record.precedents,
                    key=lambda p: p.booking_date or dt.date.min,
                    reverse=True,
                )
            }
        )
        for record in memory.suppliers
    ]
    return memory.model_copy(update={"suppliers": suppliers})


def _known(case: DatasetCase, memory: SupplierMemory) -> bool:
    """The supplier has precedents, found by IČO or, when the IČO is misread, by name."""
    supplier = case.invoice.supplier
    ico = _ico(supplier.ico)
    if ico is not None and memory.find(ico) is not None:
        return True
    name = fold(supplier.name or "")
    return bool(name) and any(fold(record.name) == name for record in memory.suppliers)


def _ico(raw: str | None) -> str | None:
    ico = "".join((raw or "").split())
    return ico if len(ico) == 8 and ico.isdigit() and ico_is_valid(ico) else None


def _customer(case: DatasetCase) -> str:
    return "".join((case.invoice.customer.ico or "").split())


def _single_entity(cases: list[DatasetCase], split: str) -> str:
    entities = sorted({_customer(c) for c in cases})
    if len(entities) != 1:
        raise ValueError(f"the {split} cases belong to {entities or 'no entity'}; pass entity")
    return entities[0]


def _booked(case: DatasetCase) -> tuple[dt.date, str]:
    return case.invoice.handwritten.date or dt.date.max, case.id
