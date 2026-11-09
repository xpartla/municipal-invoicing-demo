"""Builders for invoicing tests: fields, proposals and codings shaped like the Telekom anchor,
and an invoice in any state of the lifecycle. Pure: no database, no engine."""

from datetime import UTC, date, datetime, timedelta

from riso.contracts import Coding, CodingProposal, InvoiceDocument
from riso.invoicing.domain.invoice import (
    Actor,
    Channel,
    CodingBasis,
    Invoice,
    InvoiceState,
)

T0 = datetime(2026, 6, 23, 8, 0, tzinfo=UTC)
USER = Actor("u-jana")
BASIS = CodingBasis(year=2026, bundle_id="00305863/2026-08", version_ids=("v1", "v2"))


def fields(
    invoice_id: str = "inv-1",
    *,
    number: str | None = "144",
    booked_on: date | None = date(2026, 6, 23),
    delivered: date | None = date(2026, 6, 21),
    issued: date | None = date(2026, 6, 22),
    supplier_ico: str = "35763469",
    vs: str = "8390051427",
    gross: float = 93.71,
) -> InvoiceDocument:
    return InvoiceDocument.model_validate(
        {
            "id": invoice_id,
            "supplier": {"name": "Slovak Telekom, a.s.", "ico": supplier_ico},
            "customer": {"name": "Obec Boldog", "ico": "00305863"},
            "invoice": {
                "number": vs,
                "issue_date": issued,
                "delivery_date": delivered,
                "due_date": date(2026, 7, 7),
                "variable_symbol": vs,
                "document_type": "invoice",
            },
            "handwritten": {"date": booked_on, "number": number},
            "totals": {"gross": gross},
            "lines": [{"description": "Poplatky", "gross": gross}],
            "ocr_meta": {"synthetic": True},
        }
    )


def coding(number: str | None = "FD/144/26", *, key: str = "632005 41 01 110 000") -> Coding:
    ek, zdroj, oddiel, trieda, analytika = key.split()
    return Coding.model_validate(
        {
            "document": {"series": "FD", "number": number, "booking_date": "2026-06-23"},
            "posting": [{"md": "518 003", "dal": "321 000", "amount": 93.71, "text": "tel."}],
            "budget": [
                {
                    "key": key,
                    "ek": ek,
                    "zdroj": zdroj,
                    "oddiel": oddiel,
                    "trieda": trieda,
                    "analytika": analytika,
                    "amount": 93.71,
                    "text": "telefon,fax",
                }
            ],
        }
    )


def proposal(
    invoice_id: str = "inv-1", *, needs_review: bool = False, lines: bool = True
) -> CodingProposal:
    base = coding()
    return CodingProposal.model_validate(
        {
            "invoice_id": invoice_id,
            "bundle_id": BASIS.bundle_id,
            "document": base.document.model_dump(mode="json"),
            "supplier": {"name": "Slovak Telekom, a.s.", "ico": "35763469", "known": True},
            "invoice": {"number": "8390051427", "gross": 93.71},
            "posting": [p.model_dump(mode="json") for p in base.posting] if lines else [],
            "budget": [b.model_dump(mode="json") for b in base.budget] if lines else [],
            "confidence": {"overall": 0.6 if needs_review else 0.95},
            "validation": {"ok": True},
            "needs_review": needs_review,
        }
    )


def invoice_in(
    state: InvoiceState,
    invoice_id: str = "inv-1",
    *,
    customer_id: str = "c-boldog",
    at: datetime = T0,
) -> Invoice:
    """An invoice brought to `state` the way the lifecycle gets there. A file-based one for
    the intake states, an entered one otherwise. The history and events are cleared."""
    S = InvoiceState
    step = timedelta(minutes=1)
    if state in (S.UPLOADED, S.EXTRACTING, S.EXTRACTION_FAILED, S.DUPLICATE):
        invoice = Invoice.uploaded(
            invoice_id, customer_id, Channel.SCAN, "doc-1", at=at, actor=USER
        )
        if state is S.EXTRACTING or state is S.EXTRACTION_FAILED:
            invoice.start_extraction("job-1", at, USER)
        if state is S.EXTRACTION_FAILED:
            invoice.extraction_failed("unreadable", at, USER)
        if state is S.DUPLICATE:
            invoice.mark_duplicate("inv-0", at, USER)
    else:
        invoice = Invoice.entered(
            invoice_id, customer_id, Channel.MANUAL, fields(invoice_id), at=at, actor=USER
        )
        if state is not S.EXTRACTED and state is not S.DISCARDED:
            invoice.check(fields(invoice_id), at + step, USER)
        if state in (S.NEEDS_REVIEW, S.READY, S.BOOKED, S.EXPORTED, S.PAID):
            review = state is S.NEEDS_REVIEW
            invoice.record_coding(proposal(invoice_id, needs_review=review), BASIS, at, USER)
        if state in (S.BOOKED, S.EXPORTED, S.PAID):
            invoice.book(coding(), "accepted", "FD/144/26", at + 2 * step, USER)
        if state is S.EXPORTED:
            invoice.record_export("exp-1", at + 3 * step, USER)
        if state is S.PAID:
            invoice.mark_paid(date(2026, 7, 1), at + 3 * step, USER)
        if state is S.DISCARDED:
            invoice.discard(at + step, USER, reason="test")
    assert invoice.state is state
    invoice.history.clear()
    invoice.events.clear()
    return invoice
