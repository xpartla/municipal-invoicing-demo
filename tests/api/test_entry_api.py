"""Manual entry and the seeded dataset invoices (P2-M4-T04): after `riso seed` Boldog has the
74 dataset invoices, each coded, and every anchor's proposal is its expected coding; an
invoice typed in through the API is checked and coded at once."""

from sqlalchemy import select

from riso.dataset import load_cases
from riso.eval import compare
from riso.invoicing.infrastructure.orm import InvoiceRow
from tests.api.conftest import Fresh

CASES = {c.id: c for c in load_cases()}


def _invoices(fresh: Fresh) -> list:
    with fresh.services.uow(immediate=False) as uow:
        ids = uow.session.scalars(
            select(InvoiceRow.id).where(InvoiceRow.customer_id == fresh.boldog)
        ).all()
        return [uow.invoices.get(fresh.boldog, i) for i in ids]


def test_the_seed_gives_boldog_the_74_dataset_invoices_coded(fresh):
    invoices = _invoices(fresh)
    assert len(invoices) == len(CASES) == 74 and fresh.done.invoices == 74
    assert {i.source_ref for i in invoices} == set(CASES)
    for invoice in invoices:
        assert invoice.channel.value == "dataset" and invoice.uploaded_by is None
        assert invoice.state.value in ("needs_review", "ready"), invoice.source_ref
        assert invoice.proposal is not None and invoice.basis is not None
        assert invoice.fields is not None and invoice.fields.id == invoice.id
        assert invoice.fields.intake is not None and invoice.fields.intake.channel == "dataset"
        case = CASES[invoice.source_ref]
        expected = case.invoice.model_copy(
            update={"id": invoice.id, "intake": invoice.fields.intake}
        )
        assert invoice.fields == expected  # the fields only, never the expected coding


def test_every_anchors_proposal_is_its_expected_coding(fresh):
    anchors = [i for i in _invoices(fresh) if CASES[i.source_ref].split == "anchor"]
    assert len(anchors) == 4
    for invoice in anchors:
        case = CASES[invoice.source_ref]
        assert invoice.proposal is not None and case.expected.coding is not None
        assert compare(invoice.proposal, case) is None, invoice.source_ref
        assert invoice.proposal.document == case.expected.coding.document, invoice.source_ref


def test_an_invoice_typed_in_is_checked_and_coded(fresh):
    user = fresh.login("user")
    fields = CASES["anchor-telekom"].invoice.model_dump(mode="json") | {"id": "anything"}
    response = user.post(f"/api/customers/{fresh.boldog}/invoices", json=fields)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["channel"] == "manual" and body["state"] == "ready"
    assert body["fields"]["id"] == body["id"]
    assert body["fields"]["intake"] == {"channel": "manual", "format": None}
    assert body["proposal"]["budget"][0]["key"] == "632005 41 01 110 000"
    with fresh.services.uow(immediate=False) as uow:
        history = uow.invoices.history(fresh.boldog, body["id"])
    assert [(e.kind.value, e.to_state.value) for e in history] == [
        ("created", "extracted"),
        ("checked", "checked"),
        ("coded", "ready"),
    ]
    assert history[0].actor_id == fresh.done.users["user"][0]


def test_typed_fields_must_be_an_invoice_document(fresh):
    user = fresh.login("user")
    fields = CASES["anchor-telekom"].invoice.model_dump(mode="json")
    fields["handwritten"]["date"] = "23.6.26"
    assert user.post(f"/api/customers/{fresh.boldog}/invoices", json=fields).status_code == 422
    viewer = fresh.login("viewer")
    good = CASES["anchor-telekom"].invoice.model_dump(mode="json")
    assert viewer.post(f"/api/customers/{fresh.boldog}/invoices", json=good).status_code == 403
