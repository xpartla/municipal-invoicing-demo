"""The `Invoice` aggregate (plan §7.1): one supplier invoice from intake to payment.

    uploaded ──> extracting ──> extracted ──check──> checked ──coding──> needs_review | ready
                     │  ↑
                     ↓  └─(retry)─ extraction_failed ──(manual entry)──> extracted
    checked | needs_review | ready ──check (the fields changed)──> checked
    needs_review | ready ──coding again──> needs_review | ready
    needs_review | ready ──book──> booked ──export──> exported
    booked | exported ──mark paid──> paid           (exported and paid stay so when exported again)
    booked ──unbook──> checked                      booked ──renumber──> booked
    uploaded ──> duplicate (detected at upload)     any state before booked ──discard──> discarded

`TRANSITIONS` is the whole table, keyed by what happens and the state it happens in. Every
change appends an `InvoiceEvent`: to `history` (the repository stores the new ones in the
same transaction) and to `events` (dispatched after the commit). Paid and discarded are final
(plan §2 decision 62).

The aggregate keeps the fields as checked (`fields`, an `InvoiceDocument`), the engine's
proposal with what it was coded with (`basis`), and the booking. Which number a booking gets
is the number series' business (`numbering.py`); the invoice is told.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from riso.contracts import Coding, CodingProposal, InvoiceDocument
from riso.shared.errors import InvalidState, ValidationFailed
from riso.shared.events import DomainEvent


class InvoiceState(StrEnum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    EXTRACTION_FAILED = "extraction_failed"
    EXTRACTED = "extracted"
    CHECKED = "checked"
    NEEDS_REVIEW = "needs_review"
    READY = "ready"
    BOOKED = "booked"
    EXPORTED = "exported"
    PAID = "paid"
    DISCARDED = "discarded"
    DUPLICATE = "duplicate"


class Channel(StrEnum):
    """How the invoice came in (plan §4.3, `InvoiceDocument.intake.channel`)."""

    SCAN = "scan"
    DIGITAL_PDF = "digital_pdf"
    EINVOICE = "einvoice"
    MANUAL = "manual"
    DATASET = "dataset"

    @property
    def has_file(self) -> bool:
        """Whether the invoice starts from an uploaded file that is read by a job."""
        return self in (Channel.SCAN, Channel.DIGITAL_PDF, Channel.EINVOICE)


class EventKind(StrEnum):
    """What happened to an invoice: the history's entries."""

    CREATED = "created"
    EXTRACTION_STARTED = "extraction_started"
    EXTRACTED = "extracted"
    EXTRACTION_FAILED = "extraction_failed"
    ENTERED_MANUALLY = "entered_manually"
    MARKED_DUPLICATE = "marked_duplicate"
    CHECKED = "checked"
    CODED = "coded"
    BOOKED = "booked"
    UNBOOKED = "unbooked"
    RENUMBERED = "renumbered"
    EXPORTED = "exported"
    PAID = "paid"
    DISCARDED = "discarded"


S = InvoiceState
BEFORE_BOOKING = frozenset(
    {
        S.UPLOADED,
        S.EXTRACTING,
        S.EXTRACTION_FAILED,
        S.EXTRACTED,
        S.CHECKED,
        S.NEEDS_REVIEW,
        S.READY,
        S.DUPLICATE,
    }
)
CODED = frozenset({S.NEEDS_REVIEW, S.READY})
BOOKED_STATES = frozenset({S.BOOKED, S.EXPORTED, S.PAID})
"""The states that hold a booking."""


def _rows(
    kind: EventKind, sources: frozenset[InvoiceState] | set[InvoiceState], *targets: InvoiceState
) -> dict[tuple[EventKind, InvoiceState], frozenset[InvoiceState]]:
    return {(kind, source): frozenset(targets) for source in sources}


TRANSITIONS: Mapping[tuple[EventKind, InvoiceState], frozenset[InvoiceState]] = {
    **_rows(EventKind.EXTRACTION_STARTED, {S.UPLOADED, S.EXTRACTION_FAILED}, S.EXTRACTING),
    **_rows(EventKind.EXTRACTED, {S.EXTRACTING}, S.EXTRACTED),
    **_rows(EventKind.EXTRACTION_FAILED, {S.EXTRACTING}, S.EXTRACTION_FAILED),
    **_rows(EventKind.ENTERED_MANUALLY, {S.EXTRACTION_FAILED}, S.EXTRACTED),
    **_rows(EventKind.MARKED_DUPLICATE, {S.UPLOADED}, S.DUPLICATE),
    **_rows(EventKind.CHECKED, {S.EXTRACTED, S.CHECKED, *CODED}, S.CHECKED),
    **_rows(EventKind.CODED, {S.CHECKED, *CODED}, S.NEEDS_REVIEW, S.READY),
    **_rows(EventKind.BOOKED, CODED, S.BOOKED),
    **_rows(EventKind.UNBOOKED, {S.BOOKED}, S.CHECKED),
    **_rows(EventKind.RENUMBERED, {S.BOOKED}, S.BOOKED),
    **_rows(EventKind.EXPORTED, {S.BOOKED}, S.EXPORTED),
    **_rows(EventKind.EXPORTED, {S.EXPORTED}, S.EXPORTED),
    **_rows(EventKind.EXPORTED, {S.PAID}, S.PAID),
    **_rows(EventKind.PAID, {S.BOOKED, S.EXPORTED}, S.PAID),
    **_rows(EventKind.DISCARDED, BEFORE_BOOKING, S.DISCARDED),
}
"""Every allowed (what happens, from) and the states it may lead to. Anything else is
refused with `InvalidState`. Creating an invoice is not in the table: it starts in
`uploaded` (a file to read) or `extracted` (typed fields)."""

TIMESTAMPS: Mapping[EventKind, str] = {
    EventKind.CHECKED: "checked_at",
    EventKind.CODED: "coded_at",
    EventKind.BOOKED: "booked_at",
    EventKind.EXPORTED: "exported_at",
    EventKind.PAID: "paid_at",
    EventKind.DISCARDED: "discarded_at",
}
"""The lifecycle timestamp each event sets (plan §7.1); `uploaded_at` is the creation's.
Unbooking clears `booked_at`; the history keeps the booking."""


@dataclass(frozen=True, slots=True)
class Actor:
    """Who acts: the user, and the admin behind them when impersonating. None for a job
    started by nobody (seeding)."""

    id: str | None
    real_id: str | None = None

    @classmethod
    def system(cls) -> "Actor":
        return cls(None)


@dataclass(frozen=True, slots=True)
class InvoiceEvent(DomainEvent):
    """One entry of an invoice's history, and the domain event announcing it. `details`
    holds IDs, numbers and reasons as JSON values."""

    invoice_id: str
    customer_id: str
    kind: EventKind
    at: datetime
    actor_id: str | None
    real_actor_id: str | None
    from_state: InvoiceState | None
    to_state: InvoiceState
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CodingBasis:
    """What a proposal was coded with (plan §6.2, decision 56): the booking year, the
    reference bundle, the code list versions and the conventions revision."""

    year: int
    bundle_id: str
    version_ids: tuple[str, ...] = ()
    conventions_revision: int | None = None


BookingAction = Literal["accepted", "corrected"]


@dataclass(frozen=True, slots=True)
class Booking:
    """The coding as booked, with the number the series gave it."""

    coding: Coding
    action: BookingAction
    at: datetime
    by: str | None
    note: str | None = None

    @property
    def number(self) -> str | None:
        return self.coding.document.number

    def renumbered(self, number: str) -> "Booking":
        document = self.coding.document.model_copy(update={"number": number})
        return replace(self, coding=self.coding.model_copy(update={"document": document}))


def supply_date(fields: InvoiceDocument) -> date | None:
    """The date of supply that orders the document numbers (plan §2 decision 61): the
    printed one, else the issue date, which the VAT act lets stand for it."""
    return fields.invoice.delivery_date or fields.invoice.issue_date


@dataclass(slots=True)
class Invoice:
    id: str
    customer_id: str
    channel: Channel
    state: InvoiceState
    uploaded_at: datetime
    """When the invoice came in: the upload, the manual entry or the seeding."""
    uploaded_by: str | None
    updated_at: datetime
    document_id: str | None = None
    """The uploaded file (intake's document); None for manual and dataset invoices."""
    job_id: str | None = None
    """The extraction job the invoice waits for."""
    fields: InvoiceDocument | None = None
    """The invoice's fields: as extracted, then as checked."""
    extraction_error: str | None = None
    duplicate_of: str | None = None
    proposal: CodingProposal | None = None
    basis: CodingBasis | None = None
    coding_error: str | None = None
    """Why the last coding could not run (e.g. no code lists for the year)."""
    needs_review: bool = False
    booking: Booking | None = None
    paid_on: date | None = None
    """The payment date the user gave."""
    checked_at: datetime | None = None
    coded_at: datetime | None = None
    booked_at: datetime | None = None
    exported_at: datetime | None = None
    paid_at: datetime | None = None
    discarded_at: datetime | None = None
    discard_reason: str | None = None
    history: list[InvoiceEvent] = field(default_factory=list, repr=False)
    """History entries recorded since the invoice was loaded; the repository stores them."""
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    # Creation

    @classmethod
    def uploaded(
        cls,
        invoice_id: str,
        customer_id: str,
        channel: Channel,
        document_id: str,
        *,
        at: datetime,
        actor: Actor,
    ) -> "Invoice":
        """An invoice whose fields a job reads from the uploaded file."""
        if not channel.has_file:
            raise InvalidState(f"a {channel} invoice has no file to read")
        invoice = cls(
            id=invoice_id,
            customer_id=customer_id,
            channel=channel,
            state=S.UPLOADED,
            uploaded_at=at,
            uploaded_by=actor.id,
            updated_at=at,
            document_id=document_id,
        )
        invoice._record(EventKind.CREATED, None, at, actor, {"channel": channel.value})
        return invoice

    @classmethod
    def entered(
        cls,
        invoice_id: str,
        customer_id: str,
        channel: Channel,
        fields: InvoiceDocument,
        *,
        at: datetime,
        actor: Actor,
    ) -> "Invoice":
        """An invoice whose fields were typed (manual entry) or come from the dataset. It
        starts as extracted; checking it is the next step."""
        if channel.has_file:
            raise InvalidState(f"a {channel} invoice starts from its file")
        invoice = cls(
            id=invoice_id,
            customer_id=customer_id,
            channel=channel,
            state=S.EXTRACTED,
            uploaded_at=at,
            uploaded_by=actor.id,
            updated_at=at,
            fields=fields,
        )
        invoice._record(EventKind.CREATED, None, at, actor, {"channel": channel.value})
        return invoice

    # Queries

    @property
    def final(self) -> bool:
        return self.state in (S.PAID, S.DISCARDED)

    @property
    def booked(self) -> bool:
        return self.state in BOOKED_STATES

    @property
    def number(self) -> str | None:
        """The booked document number."""
        return self.booking.number if self.booking else None

    @property
    def supply_date(self) -> date | None:
        return supply_date(self.fields) if self.fields else None

    def awaits(self, job_id: str) -> bool:
        return self.state is S.EXTRACTING and self.job_id == job_id

    def can(self, kind: EventKind) -> bool:
        return (kind, self.state) in TRANSITIONS

    # Intake

    def start_extraction(self, job_id: str, at: datetime, actor: Actor) -> None:
        """Reads the file (again, after a failure)."""
        self._go(EventKind.EXTRACTION_STARTED, at, actor, {"job_id": job_id})
        self.job_id, self.extraction_error = job_id, None

    def extraction_succeeded(self, fields: InvoiceDocument, at: datetime, actor: Actor) -> None:
        self._go(EventKind.EXTRACTED, at, actor)
        self.fields, self.job_id = fields, None

    def extraction_failed(self, reason: str, at: datetime, actor: Actor) -> None:
        self._go(EventKind.EXTRACTION_FAILED, at, actor, {"reason": reason})
        self.job_id, self.extraction_error = None, reason

    def enter_manually(self, fields: InvoiceDocument, at: datetime, actor: Actor) -> None:
        """The fields of an invoice whose file could not be read, typed by the user."""
        self._go(EventKind.ENTERED_MANUALLY, at, actor)
        self.fields = fields

    def mark_duplicate(self, of_invoice_id: str, at: datetime, actor: Actor) -> None:
        self._go(EventKind.MARKED_DUPLICATE, at, actor, {"of": of_invoice_id})
        self.duplicate_of = of_invoice_id

    # Check and coding

    def check(self, fields: InvoiceDocument, at: datetime, actor: Actor) -> None:
        """The user confirmed the fields (again, when they changed). The proposal, which
        was coded from the earlier fields, is dropped; coding follows."""
        if fields.id != self.id:
            raise ValidationFailed.on("id", f"the fields belong to {fields.id}, not {self.id}")
        self._go(EventKind.CHECKED, at, actor)
        self.fields = fields
        self.proposal = self.basis = self.coding_error = None
        self.needs_review = False

    def record_coding(
        self, proposal: CodingProposal, basis: CodingBasis, at: datetime, actor: Actor
    ) -> None:
        """The engine's proposal for the checked fields. It needs review when S7 says so."""
        if self.fields is None or proposal.invoice_id != self.fields.id:
            raise InvalidState(f"the proposal is not for invoice {self.id}'s fields")
        target = S.NEEDS_REVIEW if proposal.needs_review else S.READY
        self._go(EventKind.CODED, at, actor, {"bundle_id": basis.bundle_id}, target=target)
        self.proposal, self.basis, self.coding_error = proposal, basis, None
        self.needs_review = proposal.needs_review

    def coding_failed(self, reason: str, at: datetime) -> None:
        """The coding could not run; the invoice stays checked without a proposal."""
        if self.state is not S.CHECKED:
            raise InvalidState(f"invoice {self.id} is {self.state}; only checked fields are coded")
        self.coding_error, self.updated_at = reason, at

    # Booking

    def book(
        self,
        coding: Coding,
        action: BookingAction,
        number: str,
        at: datetime,
        actor: Actor,
        *,
        note: str | None = None,
    ) -> None:
        """Books the coding the user accepted or corrected, under the number the series
        gave it. An accepted coding must be the proposal's; the number is not part of that
        comparison, since the series may have moved it (plan §2 decision 61)."""
        if self.proposal is None:
            raise InvalidState(f"invoice {self.id} has no proposal")
        if action == "accepted" and _without_number(coding) != _without_number(
            self.proposal.coding() if self.proposal.posting else None
        ):
            raise ValidationFailed.on(
                "action", "an accepted proposal keeps its coding; use 'corrected'"
            )
        details = {"action": action, "number": number}
        self._go(EventKind.BOOKED, at, actor, details)
        document = coding.document.model_copy(update={"number": number})
        self.booking = Booking(
            coding.model_copy(update={"document": document}), action, at, actor.id, note
        )

    def unbook(self, at: datetime, actor: Actor, *, reason: str | None = None) -> Booking:
        """Back to checked; the coding follows. Returns the booking that was undone."""
        self._go(EventKind.UNBOOKED, at, actor, {"number": self.number, "reason": reason})
        booking = self.booking
        assert booking is not None  # every booked invoice has its booking
        self.booking = self.booked_at = None
        self.proposal = self.basis = self.coding_error = None
        self.needs_review = False
        return booking

    def renumber(self, number: str, at: datetime, actor: Actor, *, because_of: str) -> None:
        """The series moved this booked invoice to `number` to make room for `because_of`
        (plan §2 decision 61). Exported and paid invoices never move."""
        old = self.number
        self._go(EventKind.RENUMBERED, at, actor, {"from": old, "to": number, "by": because_of})
        assert self.booking is not None
        self.booking = self.booking.renumbered(number)

    def record_export(self, export_run_id: str, at: datetime, actor: Actor) -> bool:
        """The invoice went into an export. Returns whether it had been exported before
        (the "already exported" notice)."""
        again = self.exported_at is not None
        self._go(EventKind.EXPORTED, at, actor, {"export_run_id": export_run_id, "again": again})
        return again

    def mark_paid(self, on: date, at: datetime, actor: Actor) -> None:
        self._go(EventKind.PAID, at, actor, {"paid_on": on.isoformat()})
        self.paid_on = on

    def discard(self, at: datetime, actor: Actor, *, reason: str | None = None) -> None:
        self._go(EventKind.DISCARDED, at, actor, {"reason": reason})
        self.discard_reason, self.job_id = reason, None

    # The table

    def _go(
        self,
        kind: EventKind,
        at: datetime,
        actor: Actor,
        details: Mapping[str, Any] | None = None,
        *,
        target: InvoiceState | None = None,
    ) -> None:
        targets = TRANSITIONS.get((kind, self.state))
        if not targets or (target is not None and target not in targets):
            raise InvalidState(f"invoice {self.id} is {self.state}; it cannot be {kind}")
        if target is None:
            (target,) = targets
        source, self.state = self.state, target
        self.updated_at = at
        if kind in TIMESTAMPS:
            setattr(self, TIMESTAMPS[kind], at)
        self._record(kind, source, at, actor, details or {})

    def _record(
        self,
        kind: EventKind,
        source: InvoiceState | None,
        at: datetime,
        actor: Actor,
        details: Mapping[str, Any],
    ) -> None:
        event = InvoiceEvent(
            self.id,
            self.customer_id,
            kind,
            at,
            actor.id,
            actor.real_id,
            source,
            self.state,
            {k: v for k, v in details.items() if v is not None},
        )
        self.history.append(event)
        self.events.append(event)


def _without_number(coding: Coding | None) -> Coding | None:
    if coding is None:
        return None
    document = coding.document.model_copy(update={"number": None})
    return coding.model_copy(update={"document": document})
