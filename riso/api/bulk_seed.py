"""`riso seed --bulk N` (P2-M8-T04, plan §2 decision 68): N synthetic invoices for Obec
Boldog, to measure the invoice table on a realistic volume.

Each is a variation of one of the dataset's cases: the same supplier, lines and amounts, its
own invoice number, variable symbol and dates, spread over 2024 to 2026. Each case is coded
once by the engine with Boldog's lists; its variations take that proposal with their own
dates, so they need no lists for 2024 and 2025. Most are booked, exported or paid, the older
the likelier paid; a few recent ones still wait for review, for the check step or were
discarded. Booked ones get their series' numbers in the order of their dates of supply,
after the numbers the series holds already. Supplier memory is left alone, so the demo's
proposals do not change. The same N and seed give the same invoices.

Dev only, like `riso seed`: the invoices are written through the repositories, without the
booking use case's placement rules, which a bulk load does not need.
"""

import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from riso import paths
from riso.api.composition import Services, build_services
from riso.contracts import CodingProposal, InvoiceDocument
from riso.dataset import load_cases
from riso.invoicing.application.coding import code_stored
from riso.invoicing.domain.invoice import Actor, Channel, CodingBasis, Invoice, InvoiceState
from riso.invoicing.domain.numbering import Holder, HolderKind, NumberSeries
from riso.platform import Settings
from riso.shared.clock import SystemClock
from riso.shared.context import RequestContext
from riso.shared.values import Ico

BOLDOG_ICO = "00305863"
FIRST_DAY = date(2024, 1, 2)
LAST_DAY = date(2026, 10, 31)
BATCH = 500
DEFAULT_PATTERNS = {"FD": "FD/XXX/RR", "FDŠJ": "FDŠJ/XXX/RR"}


class BulkSeedRefused(Exception):
    """The database has no Boldog to add invoices to."""


@dataclass(frozen=True, slots=True)
class BulkSeeded:
    invoices: int
    by_state: dict[str, int]


@dataclass(frozen=True, slots=True)
class _Prototype:
    fields: InvoiceDocument
    proposal: CodingProposal
    basis: CodingBasis

    @property
    def bookable(self) -> bool:
        return bool(self.proposal.posting) and self.proposal.validation.ok


@dataclass(slots=True)
class _Plan:
    """One invoice to write: its prototype, dates and the state it ends in."""

    prototype: _Prototype
    index: int
    booked_on: date
    supplied_on: date
    uploaded_at: datetime
    state: InvoiceState
    invoice_id: str = ""
    """Given when the invoice is written."""


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=UTC)


def _state(rng: random.Random, booked_on: date) -> InvoiceState:
    """Older invoices are paid; recent ones spread over the whole lifecycle."""
    age = (LAST_DAY - booked_on).days
    roll = rng.random()
    if age > 60:
        if roll < 0.85:
            return InvoiceState.PAID
        return InvoiceState.EXPORTED if roll < 0.95 else InvoiceState.BOOKED
    for limit, state in (
        (0.30, InvoiceState.PAID),
        (0.55, InvoiceState.EXPORTED),
        (0.80, InvoiceState.BOOKED),
        (0.88, InvoiceState.NEEDS_REVIEW),
        (0.93, InvoiceState.READY),
        (0.97, InvoiceState.EXTRACTED),
    ):
        if roll < limit:
            return state
    return InvoiceState.DISCARDED


def _plans(prototypes: list[_Prototype], count: int, seed: int) -> list[_Plan]:
    rng = random.Random(seed)
    span = (LAST_DAY - FIRST_DAY).days
    bookable = [p for p in prototypes if p.bookable]
    plans = []
    for index in range(count):
        booked_on = FIRST_DAY + timedelta(days=rng.randrange(span + 1))
        state = _state(rng, booked_on)
        pool = bookable if state in _BOOKED or state is InvoiceState.READY else prototypes
        prototype = pool[rng.randrange(len(pool))]
        supplied_on = booked_on - timedelta(days=rng.randrange(0, 21))
        uploaded_at = _at(booked_on, 7 + rng.randrange(9), rng.randrange(60)) - timedelta(
            days=rng.randrange(0, 4)
        )
        plans.append(_Plan(prototype, index, booked_on, supplied_on, uploaded_at, state))
    return plans


_BOOKED = {InvoiceState.BOOKED, InvoiceState.EXPORTED, InvoiceState.PAID}


def _fields(plan: _Plan, invoice_id: str) -> InvoiceDocument:
    """The prototype's fields with this invoice's own numbers and dates."""
    base = plan.prototype.fields
    number = f"B{plan.booked_on:%y}{plan.index:06d}"
    issued = plan.supplied_on
    invoice = base.invoice.model_copy(
        update={
            "number": number,
            "variable_symbol": number[1:],
            "issue_date": issued,
            "delivery_date": plan.supplied_on,
            "due_date": issued + timedelta(days=14),
        }
    )
    handwritten = base.handwritten.model_copy(update={"date": plan.booked_on, "number": None})
    return base.model_copy(
        update={"id": invoice_id, "invoice": invoice, "handwritten": handwritten}
    )


def _proposal(plan: _Plan, invoice_id: str, fields: InvoiceDocument) -> CodingProposal:
    """The prototype's proposal for this invoice: its ID, booking date and invoice number."""
    proposal = plan.prototype.proposal
    document = proposal.document.model_copy(update={"booking_date": plan.booked_on, "number": None})
    summary = proposal.invoice.model_copy(
        update={"number": fields.invoice.number, "vs": fields.invoice.variable_symbol}
    )
    return proposal.model_copy(
        update={"invoice_id": invoice_id, "document": document, "invoice": summary}
    )


def seed_bulk(
    settings: Settings,
    count: int,
    *,
    seed: int = 2026,
    invoices_dir: Path = paths.INVOICES_DIR,
) -> BulkSeeded:
    """Adds `count` synthetic invoices to Boldog in the database of `settings`."""
    services = build_services(settings, clock=SystemClock())
    ctx = RequestContext.system("seed")
    actor = Actor.system()
    try:
        with services.uow() as uow:
            boldog = uow.customers.find_active_by_ico(Ico(BOLDOG_ICO))
        if boldog is None:
            raise BulkSeedRefused("the database has no Obec Boldog; run `riso seed` first")
        customer_id = boldog.id
        prototypes = _prototypes(services, ctx, actor, customer_id, invoices_dir)
        plans = _plans(prototypes, count, seed)
        numbers = _numbers(services, customer_id, plans)
        by_state: dict[str, int] = defaultdict(int)
        for start in range(0, len(plans), BATCH):
            with services.uow() as uow:
                for plan in plans[start : start + BATCH]:
                    plan.invoice_id = uow.ids.new()
                    invoice = _invoice(plan.invoice_id, customer_id, plan, numbers, actor)
                    uow.invoices.add(invoice)
                    by_state[invoice.state.value] += 1
                uow.commit()
        _hold(services, customer_id, plans, numbers)
        with services.uow() as uow:
            uow.audit.record(
                ctx,
                "invoice.bulk_seeded",
                target_type="customer",
                target_id=customer_id,
                customer_id=customer_id,
                details={"count": count, "seed": seed},
            )
            uow.commit()
        return BulkSeeded(count, dict(sorted(by_state.items())))
    finally:
        services.close()


def _prototypes(
    services: Services, ctx: RequestContext, actor: Actor, customer_id: str, root: Path
) -> list[_Prototype]:
    """Each dataset case coded once with Boldog's lists, in a transaction that is not kept."""
    reference = services.reference_data()
    prototypes = []
    with services.uow() as uow:
        for case in load_cases(root):
            invoice_id = uow.ids.new()
            fields = case.invoice.model_copy(update={"id": invoice_id})
            invoice = Invoice.entered(
                invoice_id, customer_id, Channel.MANUAL, fields, at=uow.clock.now(), actor=actor
            )
            invoice.check(fields, uow.clock.now(), actor)
            code_stored(ctx, uow, reference, invoice, actor)
            if invoice.proposal is not None and invoice.basis is not None:
                prototypes.append(_Prototype(case.invoice, invoice.proposal, invoice.basis))
        # Nothing coded here is stored: the unit of work rolls back on leaving.
    if not prototypes:
        raise BulkSeedRefused("no dataset case could be coded with Boldog's lists")
    return prototypes


@dataclass(frozen=True, slots=True)
class _Number:
    series: str
    year: int
    sequence: int
    text: str
    frozen: bool


def _numbers(services: Services, customer_id: str, plans: list[_Plan]) -> dict[int, _Number]:
    """The document number of each booked plan: per series and year, in the order of the
    dates of supply, after the highest number the series holds already."""
    groups: dict[tuple[str, int], list[_Plan]] = defaultdict(list)
    for plan in plans:
        if plan.state in _BOOKED:
            groups[(plan.prototype.proposal.document.series, plan.booked_on.year)].append(plan)
    numbers: dict[int, _Number] = {}
    with services.uow() as uow:
        for (series, year), group in groups.items():
            stored = uow.number_series.find(customer_id, series, year)
            pattern = (
                stored.pattern
                if stored is not None
                else _pattern(uow.series_patterns.patterns(customer_id, year), series)
            )
            transient = NumberSeries.new("n", customer_id, series, year, pattern, _at(LAST_DAY, 0))
            start = max(stored.highest, stored.last_used) if stored is not None else 0
            group.sort(key=lambda p: (p.supplied_on, p.uploaded_at, p.index))
            for offset, plan in enumerate(group, start=1):
                sequence = start + offset
                numbers[plan.index] = _Number(
                    series,
                    year,
                    sequence,
                    transient.number(sequence),
                    plan.state is not InvoiceState.BOOKED,
                )
    return numbers


def _pattern(patterns: dict[str, str], series: str) -> str:
    return patterns.get(series) or DEFAULT_PATTERNS.get(series) or f"{series}/XXX/RR"


def _invoice(
    invoice_id: str, customer_id: str, plan: _Plan, numbers: dict[int, _Number], actor: Actor
) -> Invoice:
    fields = _fields(plan, invoice_id)
    uploaded = plan.uploaded_at
    invoice = Invoice.entered(
        invoice_id, customer_id, Channel.MANUAL, fields, at=uploaded, actor=actor
    )
    if plan.state is InvoiceState.EXTRACTED:
        return invoice
    if plan.state is InvoiceState.DISCARDED:
        invoice.discard(uploaded + timedelta(hours=2), actor, reason="duplicitná")
        return invoice
    checked = uploaded + timedelta(minutes=20)
    invoice.check(fields, checked, actor)
    proposal = _proposal(plan, invoice_id, fields)
    if plan.state is InvoiceState.NEEDS_REVIEW:
        proposal = proposal.model_copy(update={"needs_review": True})
    elif plan.state is InvoiceState.READY:
        proposal = proposal.model_copy(update={"needs_review": False, "review_reasons": []})
    invoice.record_coding(proposal, plan.prototype.basis, checked, actor)
    if plan.state not in _BOOKED:
        return invoice
    number = numbers[plan.index]
    booked = _at(plan.booked_on, 15, plan.index % 60)
    invoice.book(proposal.coding(), "accepted", number.text, booked, actor)
    if plan.state in (InvoiceState.EXPORTED, InvoiceState.PAID):
        invoice.record_export("bulk-seed", booked + timedelta(days=3), actor)
    if plan.state is InvoiceState.PAID:
        paid_on = plan.booked_on + timedelta(days=10)
        invoice.mark_paid(paid_on, _at(paid_on, 9), actor)
    return invoice


def _hold(
    services: Services, customer_id: str, plans: list[_Plan], numbers: dict[int, _Number]
) -> None:
    """The series hold the booked invoices' numbers, as a booking would have left them."""
    groups: dict[tuple[str, int], list[tuple[_Plan, _Number]]] = defaultdict(list)
    for plan in plans:
        number = numbers.get(plan.index)
        if number is not None:
            groups[(number.series, number.year)].append((plan, number))
    with services.uow() as uow:
        for (series, year), held in groups.items():
            stored = uow.number_series.find(customer_id, series, year)
            new = stored is None
            if stored is None:
                pattern = _pattern(uow.series_patterns.patterns(customer_id, year), series)
                stored = NumberSeries.new(
                    uow.ids.new(), customer_id, series, year, pattern, uow.clock.now()
                )
            for plan, number in held:
                stored.holders.append(
                    Holder(
                        uow.ids.new(),
                        number.sequence,
                        HolderKind.BOOKED,
                        plan.invoice_id,
                        plan.supplied_on,
                        plan.uploaded_at,
                        frozen=number.frozen,
                    )
                )
            stored.last_used = max(stored.last_used, stored.highest)
            stored.updated_at = uow.clock.now()
            if new:
                uow.number_series.add(stored)
            else:
                uow.number_series.save(stored)
        uow.commit()
