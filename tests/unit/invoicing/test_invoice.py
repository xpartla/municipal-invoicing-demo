"""The `Invoice` aggregate (P2-M4-T01): every allowed transition with its timestamp and
event, every other one refused, and the guards of each step."""

from collections.abc import Callable
from datetime import date, timedelta

import pytest

from riso.invoicing.domain.invoice import (
    TIMESTAMPS,
    TRANSITIONS,
    Actor,
    Channel,
    EventKind,
    Invoice,
    InvoiceEvent,
    InvoiceState,
    supply_date,
)
from riso.shared import InvalidState, ValidationFailed
from tests.fakes.invoicing import BASIS, T0, USER, coding, fields, invoice_in, proposal

S = InvoiceState
AT = T0 + timedelta(hours=1)
ADMIN_AS_JANA = Actor("u-jana", real_id="u-admin")

ACTIONS: dict[EventKind, Callable[[Invoice], object]] = {
    EventKind.EXTRACTION_STARTED: lambda i: i.start_extraction("job-2", AT, ADMIN_AS_JANA),
    EventKind.EXTRACTED: lambda i: i.extraction_succeeded(fields(i.id), AT, ADMIN_AS_JANA),
    EventKind.EXTRACTION_FAILED: lambda i: i.extraction_failed("blurred", AT, ADMIN_AS_JANA),
    EventKind.ENTERED_MANUALLY: lambda i: i.enter_manually(fields(i.id), AT, ADMIN_AS_JANA),
    EventKind.MARKED_DUPLICATE: lambda i: i.mark_duplicate("inv-0", AT, ADMIN_AS_JANA),
    EventKind.CHECKED: lambda i: i.check(fields(i.id), AT, ADMIN_AS_JANA),
    EventKind.CODED: lambda i: i.record_coding(
        proposal(i.id, needs_review=True), BASIS, AT, ADMIN_AS_JANA
    ),
    EventKind.BOOKED: lambda i: i.book(coding(), "corrected", "FD/144/26", AT, ADMIN_AS_JANA),
    EventKind.UNBOOKED: lambda i: i.unbook(AT, ADMIN_AS_JANA),
    EventKind.RENUMBERED: lambda i: i.renumber("FD/145/26", AT, ADMIN_AS_JANA, because_of="x"),
    EventKind.EXPORTED: lambda i: i.record_export("exp-2", AT, ADMIN_AS_JANA),
    EventKind.PAID: lambda i: i.mark_paid(date(2026, 7, 2), AT, ADMIN_AS_JANA),
    EventKind.DISCARDED: lambda i: i.discard(AT, ADMIN_AS_JANA, reason="wrong customer"),
}


def test_every_event_but_creation_has_an_action():
    assert set(ACTIONS) == set(EventKind) - {EventKind.CREATED}
    assert {kind for kind, _ in TRANSITIONS} == set(ACTIONS)


@pytest.mark.parametrize("state", list(InvoiceState))
@pytest.mark.parametrize("kind", list(ACTIONS))
def test_the_transition_table(kind, state):
    invoice = invoice_in(state)
    before = invoice.updated_at
    targets = TRANSITIONS.get((kind, state))
    if targets is None:
        with pytest.raises(InvalidState):
            ACTIONS[kind](invoice)
        assert invoice.state is state
        assert invoice.updated_at == before
        assert invoice.history == [] and invoice.events == []
        return
    ACTIONS[kind](invoice)
    assert invoice.state in targets
    assert invoice.updated_at == AT
    if kind in TIMESTAMPS:
        assert getattr(invoice, TIMESTAMPS[kind]) == AT
    (event,) = invoice.history
    assert event.kind is kind
    assert (event.from_state, event.to_state) == (state, invoice.state)
    assert (event.at, event.actor_id, event.real_actor_id) == (AT, "u-jana", "u-admin")
    assert (event.invoice_id, event.customer_id) == ("inv-1", "c-boldog")
    assert invoice.events == [event]


def test_paid_and_discarded_are_final():
    assert {s for s in S if invoice_in(s).final} == {S.PAID, S.DISCARDED}
    assert not any(source is S.DISCARDED for _, source in TRANSITIONS)
    # Exporting is the one thing that still happens to a paid invoice, and it stays paid.
    assert {kind for kind, source in TRANSITIONS if source is S.PAID} == {EventKind.EXPORTED}
    assert TRANSITIONS[(EventKind.EXPORTED, S.PAID)] == {S.PAID}


def test_an_uploaded_invoice_waits_for_its_file_to_be_read():
    invoice = Invoice.uploaded("inv-1", "c1", Channel.SCAN, "doc-1", at=T0, actor=USER)
    assert (invoice.state, invoice.document_id, invoice.fields) == (S.UPLOADED, "doc-1", None)
    assert (invoice.uploaded_at, invoice.uploaded_by) == (T0, "u-jana")
    (event,) = invoice.events
    assert isinstance(event, InvoiceEvent)
    assert (event.kind, event.from_state, event.to_state) == (EventKind.CREATED, None, S.UPLOADED)
    assert event.details == {"channel": "scan"}
    with pytest.raises(InvalidState, match="no file"):
        Invoice.uploaded("inv-2", "c1", Channel.MANUAL, "doc-1", at=T0, actor=USER)


def test_an_entered_invoice_starts_extracted_with_its_fields():
    invoice = Invoice.entered("inv-1", "c1", Channel.DATASET, fields(), at=T0, actor=USER)
    assert invoice.state is S.EXTRACTED and invoice.fields == fields()
    assert invoice.history[0].details == {"channel": "dataset"}
    with pytest.raises(InvalidState, match="starts from its file"):
        Invoice.entered("inv-2", "c1", Channel.EINVOICE, fields("inv-2"), at=T0, actor=USER)


def test_the_extraction_job_is_awaited_and_its_failure_kept():
    invoice = invoice_in(S.UPLOADED)
    invoice.start_extraction("job-7", T0, USER)
    assert invoice.awaits("job-7") and not invoice.awaits("job-6")
    invoice.extraction_failed("blurred", T0, USER)
    assert not invoice.awaits("job-7") and invoice.extraction_error == "blurred"
    invoice.start_extraction("job-8", T0, USER)  # a retry
    assert invoice.extraction_error is None and invoice.awaits("job-8")
    invoice.extraction_succeeded(fields(), T0, USER)
    assert invoice.state is S.EXTRACTED and invoice.fields == fields()
    assert invoice.job_id is None


def test_manual_entry_after_a_failed_extraction():
    invoice = invoice_in(S.EXTRACTION_FAILED)
    invoice.enter_manually(fields(), T0, USER)
    assert invoice.state is S.EXTRACTED and invoice.fields == fields()


def test_checking_stores_the_fields_and_drops_the_old_proposal():
    invoice = invoice_in(S.NEEDS_REVIEW)
    assert invoice.proposal is not None and invoice.needs_review
    changed = fields(number="145")
    invoice.check(changed, AT, USER)
    assert invoice.state is S.CHECKED and invoice.fields == changed
    assert (invoice.proposal, invoice.basis, invoice.needs_review) == (None, None, False)
    assert invoice.checked_at == AT


def test_the_fields_must_be_the_invoices():
    invoice = invoice_in(S.EXTRACTED)
    with pytest.raises(ValidationFailed) as raised:
        invoice.check(fields("inv-2"), AT, USER)
    assert raised.value.errors[0].field == "id"
    assert invoice.state is S.EXTRACTED


@pytest.mark.parametrize(("review", "state"), [(True, S.NEEDS_REVIEW), (False, S.READY)])
def test_the_coding_follows_the_review_flag(review, state):
    invoice = invoice_in(S.CHECKED)
    invoice.record_coding(proposal(needs_review=review), BASIS, AT, USER)
    assert invoice.state is state and invoice.needs_review is review
    assert (invoice.basis, invoice.coded_at) == (BASIS, AT)
    assert invoice.history[0].details == {"bundle_id": BASIS.bundle_id}
    invoice.record_coding(proposal(needs_review=not review), BASIS, AT, USER)  # re-coding
    assert invoice.needs_review is not review


def test_a_proposal_for_other_fields_is_refused():
    invoice = invoice_in(S.CHECKED)
    with pytest.raises(InvalidState, match="not for invoice"):
        invoice.record_coding(proposal("inv-2"), BASIS, AT, USER)


def test_a_coding_that_cannot_run_leaves_the_invoice_checked():
    invoice = invoice_in(S.CHECKED)
    invoice.coding_failed("no code lists for 2027", AT)
    assert invoice.state is S.CHECKED and invoice.coding_error == "no code lists for 2027"
    invoice.record_coding(proposal(), BASIS, AT, USER)
    assert invoice.coding_error is None
    with pytest.raises(InvalidState):
        invoice.coding_failed("again", AT)


def test_booking_takes_the_number_the_series_gives():
    invoice = invoice_in(S.READY)
    invoice.book(coding(), "accepted", "FD/145/26", AT, USER, note="ok")
    assert invoice.state is S.BOOKED and invoice.booked_at == AT
    assert invoice.number == "FD/145/26"
    assert invoice.booking is not None
    assert (invoice.booking.action, invoice.booking.by, invoice.booking.note) == (
        "accepted",
        "u-jana",
        "ok",
    )
    assert invoice.booking.coding.budget == coding().budget
    assert invoice.history[0].details == {"action": "accepted", "number": "FD/145/26"}


def test_an_accepted_booking_must_be_the_proposal():
    invoice = invoice_in(S.NEEDS_REVIEW)
    other = coding(key="632003 41 01 110 001")
    with pytest.raises(ValidationFailed, match="use 'corrected'"):
        invoice.book(other, "accepted", "FD/144/26", AT, USER)
    assert invoice.state is S.NEEDS_REVIEW
    invoice.book(other, "corrected", "FD/144/26", AT, USER)
    assert invoice.booking is not None and invoice.booking.action == "corrected"


def test_a_proposal_without_lines_is_booked_only_as_entered_by_hand():
    invoice = invoice_in(S.CHECKED)
    invoice.record_coding(proposal(needs_review=True, lines=False), BASIS, AT, USER)
    with pytest.raises(ValidationFailed):
        invoice.book(coding(), "accepted", "FD/144/26", AT, USER)
    invoice.book(coding(), "corrected", "FD/144/26", AT, USER)
    assert invoice.state is S.BOOKED


def test_unbooking_returns_the_booking_and_clears_it():
    invoice = invoice_in(S.BOOKED)
    booking = invoice.booking
    undone = invoice.unbook(AT, USER, reason="wrong supplier")
    assert undone == booking
    assert invoice.state is S.CHECKED
    assert (invoice.booking, invoice.booked_at, invoice.proposal) == (None, None, None)
    assert invoice.history[0].details == {"number": "FD/144/26", "reason": "wrong supplier"}


def test_renumbering_moves_the_booked_number():
    invoice = invoice_in(S.BOOKED)
    invoice.renumber("FD/145/26", AT, USER, because_of="inv-9")
    assert invoice.number == "FD/145/26" and invoice.state is S.BOOKED
    assert invoice.booking is not None
    assert invoice.booking.coding.document.booking_date == date(2026, 6, 23)
    assert invoice.history[0].details == {"from": "FD/144/26", "to": "FD/145/26", "by": "inv-9"}


@pytest.mark.parametrize("state", [S.EXPORTED, S.PAID])
def test_exported_and_paid_invoices_keep_their_number(state):
    invoice = invoice_in(state)
    with pytest.raises(InvalidState):
        invoice.renumber("FD/145/26", AT, USER, because_of="inv-9")
    assert invoice.number == "FD/144/26"


def test_exporting_again_keeps_the_state_and_says_so():
    invoice = invoice_in(S.BOOKED)
    assert invoice.record_export("exp-1", AT, USER) is False
    assert invoice.state is S.EXPORTED and invoice.exported_at == AT
    later = AT + timedelta(days=1)
    assert invoice.record_export("exp-2", later, USER) is True
    assert invoice.state is S.EXPORTED and invoice.exported_at == later
    assert [e.details for e in invoice.history] == [
        {"export_run_id": "exp-1", "again": False},
        {"export_run_id": "exp-2", "again": True},
    ]


def test_a_paid_invoice_can_be_exported_and_stays_paid():
    invoice = invoice_in(S.PAID)
    assert invoice.exported_at is None
    assert invoice.record_export("exp-1", AT, USER) is False
    assert invoice.state is S.PAID and invoice.exported_at == AT


def test_paying_keeps_the_export():
    invoice = invoice_in(S.EXPORTED)
    exported = invoice.exported_at
    invoice.mark_paid(date(2026, 7, 2), AT, USER)
    assert invoice.state is S.PAID and invoice.paid_on == date(2026, 7, 2)
    assert invoice.paid_at == AT and invoice.exported_at == exported
    assert invoice.history[0].details == {"paid_on": "2026-07-02"}


def test_discarding_keeps_the_reason():
    invoice = invoice_in(S.EXTRACTING)
    invoice.discard(AT, USER, reason="not ours")
    assert invoice.state is S.DISCARDED and invoice.final
    assert (invoice.discard_reason, invoice.job_id, invoice.discarded_at) == ("not ours", None, AT)
    plain = invoice_in(S.READY)
    plain.discard(AT, USER)
    assert plain.history[0].details == {}  # no reason, nothing recorded


def test_the_supply_date_falls_back_to_the_issue_date():
    assert supply_date(fields()) == date(2026, 6, 21)
    assert supply_date(fields(delivered=None)) == date(2026, 6, 22)
    assert supply_date(fields(delivered=None, issued=None)) is None
    assert invoice_in(S.CHECKED).supply_date == date(2026, 6, 21)
    assert invoice_in(S.UPLOADED).supply_date is None


def test_the_booked_states():
    assert {s for s in S if invoice_in(s).booked} == {S.BOOKED, S.EXPORTED, S.PAID}
    assert invoice_in(S.READY).number is None
