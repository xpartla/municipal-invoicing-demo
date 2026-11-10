"""The invoice table and the bulk actions (P2-M4-T05): every filter of plan §10.3 and every
sort, checked against the seeded invoices read through the repository; paging; foreign
customers; the detail and the history; bulk actions reporting each invoice."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from riso.invoicing.domain.invoice import Actor
from riso.invoicing.infrastructure.invoice_repo import searchable
from riso.invoicing.infrastructure.orm import InvoiceRow
from tests.api.conftest import Fresh
from tests.factories import make_invoice

TELEKOM = "35763469"


@pytest.fixture(scope="module")
def table(seeded):
    """(app, done, the seeded invoices by ID) for read-only tests."""
    app, done, _ = seeded
    services = app.state.services
    boldog = done.customers["Obec Boldog"]
    with services.uow(immediate=False) as uow:
        ids = uow.session.scalars(
            select(InvoiceRow.id).where(InvoiceRow.customer_id == boldog)
        ).all()
        invoices = {i: uow.invoices.get(boldog, i) for i in ids}
    return app, done, boldog, invoices


def _ids(client, boldog, **params) -> list[str]:
    params.setdefault("size", 200)
    response = client.get(f"/api/customers/{boldog}/invoices", params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == len(body["items"])
    return [row["id"] for row in body["items"]]


def _expect(invoices, keep) -> set[str]:
    return {i for i, invoice in invoices.items() if keep(invoice)}


def _lines(invoice):
    proposal = invoice.proposal
    return list(zip(proposal.posting, proposal.budget, strict=False)) if proposal else []


@pytest.fixture
def viewer(table, login):
    return login("viewer")


def test_without_filters_every_invoice_newest_first(table, viewer):
    _, _, boldog, invoices = table
    ids = _ids(viewer, boldog)
    assert set(ids) == set(invoices) and len(ids) == 74


@pytest.mark.parametrize(
    ("params", "keep"),
    [
        ({"q": "telekom"}, lambda i: "telekom" in searchable(i.fields.supplier.name or "")),
        (
            {"q": "SLOVAK   TELEKOM"},
            lambda i: "slovak telekom" in searchable(i.fields.supplier.name or ""),
        ),
        ({"supplier_ico": TELEKOM}, lambda i: i.proposal.supplier.ico == TELEKOM),
        ({"state": "ready"}, lambda i: i.state.value == "ready"),
        ({"state": ["ready", "needs_review"]}, lambda i: True),
        ({"series": "FDŠJ"}, lambda i: i.proposal.document.series == "FDŠJ"),
        ({"channel": "dataset"}, lambda i: True),
        ({"channel": "manual"}, lambda i: False),
        ({"needs_review": "true"}, lambda i: i.needs_review),
        ({"needs_review": "false"}, lambda i: not i.needs_review),
        ({"uploaded_by": "someone"}, lambda i: False),
        (
            {"issue_from": "2026-06-01", "issue_to": "2026-06-30"},
            lambda i: (
                date(2026, 6, 1) <= (i.fields.invoice.issue_date or date.min) <= date(2026, 6, 30)
            ),
        ),
        (
            {"due_from": "2026-07-01"},
            lambda i: (i.fields.invoice.due_date or date.min) >= date(2026, 7, 1),
        ),
        (
            {"booking_to": "2026-05-31"},
            lambda i: (
                i.proposal.document.booking_date is not None
                and i.proposal.document.booking_date <= date(2026, 5, 31)
            ),
        ),
        ({"uploaded_from": "2026-01-01", "uploaded_to": "2026-01-01"}, lambda i: True),
        ({"uploaded_to": "2025-12-31"}, lambda i: False),
        (
            {"amount_min": "100", "amount_max": "500.5"},
            lambda i: (
                i.fields.totals.gross is not None
                and Decimal(100) <= i.fields.totals.gross <= Decimal("500.5")
            ),
        ),
        ({"budget": "632"}, lambda i: any(b.key.startswith("632") for _, b in _lines(i))),
        (
            {"budget": "632005 41"},
            lambda i: any(b.key.startswith("632005 41") for _, b in _lines(i)),
        ),
        ({"md": "518"}, lambda i: any(p.md.startswith("518") for p, _ in _lines(i))),
        ({"dal": "321 000"}, lambda i: any(p.dal == "321 000" for p, _ in _lines(i))),
        (
            {"budget": "637", "md": "518"},
            lambda i: any(b.key.startswith("637") and p.md.startswith("518") for p, b in _lines(i)),
        ),
    ],
    ids=lambda v: str(v)[:40] if isinstance(v, dict) else "",
)
def test_each_filter(table, viewer, params, keep):
    _, _, boldog, invoices = table
    expected = _expect(invoices, keep)
    assert set(_ids(viewer, boldog, **params)) == expected
    if params not in (
        {"channel": "manual"},
        {"uploaded_by": "someone"},
        {"uploaded_to": "2025-12-31"},
    ):
        assert expected, "a filter that finds nothing proves little"


def _printed(ico: str | None) -> str | None:
    """The IČO as printed, when the engine dropped it (a failing check digit)."""
    digits = "".join(c for c in ico or "" if c.isdigit())
    return digits.zfill(8) if 6 <= len(digits) <= 8 else None


def _key(invoice, key: str):
    fields, proposal = invoice.fields, invoice.proposal
    return {
        "state": invoice.state.value,
        "document_number": proposal.document.number,
        "booking_date": proposal.document.booking_date,
        "supplier_name": proposal.supplier.name or fields.supplier.name,
        "supplier_ico": proposal.supplier.ico or _printed(fields.supplier.ico),
        "invoice_number": fields.invoice.number,
        "variable_symbol": fields.invoice.variable_symbol,
        "issue_date": fields.invoice.issue_date,
        "due_date": fields.invoice.due_date,
        "supply_date": invoice.supply_date,
        "gross": fields.totals.gross.quantize(Decimal("0.01")) if fields.totals.gross else None,
        "uploaded_at": invoice.uploaded_at,
        "exported_at": invoice.exported_at,
        "paid_on": invoice.paid_on,
    }[key]


SORTS = [
    "state",
    "document_number",
    "booking_date",
    "supplier_name",
    "supplier_ico",
    "invoice_number",
    "variable_symbol",
    "issue_date",
    "due_date",
    "supply_date",
    "gross",
    "uploaded_at",
    "exported_at",
    "paid_on",
]


@pytest.mark.parametrize("descending", [False, True])
@pytest.mark.parametrize("key", SORTS)
def test_each_sort(table, viewer, key, descending):
    _, _, boldog, invoices = table
    ids = _ids(viewer, boldog, sort=("-" if descending else "") + key)
    values = [_key(invoices[i], key) for i in ids]
    present = [v for v in values if v is not None]
    assert values == present + [None] * (len(values) - len(present))  # empty values last
    assert present == sorted(present, reverse=descending)
    # Ties follow the ID, in the sort's direction.
    for a, b in zip(ids, ids[1:], strict=False):
        if _key(invoices[a], key) == _key(invoices[b], key):
            assert (a > b) if descending else (a < b)


def test_an_unknown_sort_is_refused(table, viewer):
    _, _, boldog, _ = table
    response = viewer.get(f"/api/customers/{boldog}/invoices", params={"sort": "-password"})
    assert response.status_code == 422


def test_paging_goes_through_every_invoice_once(table, viewer):
    _, _, boldog, invoices = table
    seen = []
    for page in range(1, 9):
        body = viewer.get(
            f"/api/customers/{boldog}/invoices", params={"page": page, "size": 10}
        ).json()
        assert body["total"] == 74
        seen += [row["id"] for row in body["items"]]
    assert len(seen) == 74 and set(seen) == set(invoices)
    too_big = viewer.get(f"/api/customers/{boldog}/invoices", params={"size": 201})
    assert too_big.status_code == 422


def test_a_row_carries_the_table_columns(table, viewer):
    _, _, boldog, invoices = table
    response = viewer.get(f"/api/customers/{boldog}/invoices", params={"q": "8390051427"})
    (row,) = [r for r in response.json()["items"] if r["source_ref"] == "anchor-telekom"]
    assert row["document_number"] == "FD/144/26" and row["series"] == "FD"
    assert row["booking_date"] == "2026-06-23" and row["gross"] == 93.71
    assert row["budget_keys"] == ["632005 41 01 110 000"]
    assert (row["md"], row["dal"]) == (["518 003"], ["321 000"])
    assert row["supplier_ico"] == TELEKOM and row["channel"] == "dataset"


def test_the_supplier_filter_suggests_suppliers(table, viewer):
    _, _, boldog, _ = table
    response = viewer.get(f"/api/customers/{boldog}/invoices/suppliers", params={"q": "telek"})
    assert response.status_code == 200
    found = response.json()
    assert found[0]["ico"] == TELEKOM and found[0]["invoices"] >= 2
    assert all("telek" in searchable(s["name"]) for s in found)
    by_ico = viewer.get(f"/api/customers/{boldog}/invoices/suppliers", params={"q": TELEKOM})
    assert [s["ico"] for s in by_ico.json()] == [TELEKOM]


def test_another_customers_invoices_are_not_found(table, login):
    _, done, boldog, invoices = table
    other = done.customers["Obec Vzorová Lehota"]
    alone = done.customers["Obec Nezávislá"]
    an_invoice = next(iter(invoices))
    user, staff = login("user"), login("staff")
    assert user.get(f"/api/customers/{other}/invoices").status_code == 404
    assert staff.get(f"/api/customers/{alone}/invoices").status_code == 404
    assert staff.get(f"/api/customers/{other}/invoices").json()["total"] == 0
    assert staff.get(f"/api/customers/{other}/invoices/{an_invoice}").status_code == 404
    assert staff.get(f"/api/customers/{other}/invoices/{an_invoice}/history").status_code == 404
    response = staff.post(
        f"/api/customers/{other}/invoices/bulk/recode", json={"invoice_ids": [an_invoice]}
    )
    assert response.json()["results"] == [
        {
            "invoice_id": an_invoice,
            "ok": False,
            "code": "not_found",
            "message": response.json()["results"][0]["message"],
        }
    ]


def test_the_detail_and_the_history(fresh: Fresh):
    user = fresh.login("user")
    invoice_id = make_invoice(fresh.services, fresh.boldog, "anchor-telekom")
    detail = user.get(f"/api/customers/{fresh.boldog}/invoices/{invoice_id}")
    assert detail.status_code == 200
    proposal = detail.json()["proposal"]
    coding = {k: proposal[k] for k in ("document", "posting", "budget")}
    user.post(
        f"/api/customers/{fresh.boldog}/invoices/{invoice_id}/book",
        json={"action": "accepted", "coding": coding},
    )
    history = user.get(f"/api/customers/{fresh.boldog}/invoices/{invoice_id}/history").json()
    assert [(e["kind"], e["to_state"]) for e in history["items"]] == [
        ("created", "extracted"),
        ("checked", "checked"),
        ("coded", "ready"),
        ("booked", "booked"),
    ]
    jana = fresh.done.users["user"][0]
    assert history["items"][-1]["actor_id"] == jana
    assert history["items"][0]["actor_id"] is None  # the factory acts as the system
    assert history["names"] == {jana: "Jana Vzorová"}


def test_the_exported_and_paid_filters(fresh: Fresh):
    user = fresh.login("user")
    booked = make_invoice(fresh.services, fresh.boldog, "anchor-telekom")
    with fresh.services.uow() as uow:
        invoice = uow.invoices.get(fresh.boldog, booked)
        assert invoice.proposal is not None
        invoice.book(
            invoice.proposal.coding(), "accepted", "FD/144/26", invoice.uploaded_at, Actor("x")
        )
        invoice.record_export("exp", datetime(2026, 7, 1, 22, 30, tzinfo=UTC), Actor("x"))
        uow.invoices.save(invoice)
        uow.commit()
    # 22:30 UTC on 1 July is 00:30 on 2 July in Bratislava (CEST).
    assert _ids(user, fresh.boldog, exported_from="2026-07-02") == [booked]
    assert _ids(user, fresh.boldog, exported_to="2026-07-01") == []
    paid = user.post(
        f"/api/customers/{fresh.boldog}/invoices/{booked}/pay", json={"paid_on": "2026-07-05"}
    )
    assert paid.status_code == 200
    assert _ids(user, fresh.boldog, paid_from="2026-07-05", paid_to="2026-07-05") == [booked]
    assert _ids(user, fresh.boldog, state="paid") == [booked]
    mine = user.post(
        f"/api/customers/{fresh.boldog}/invoices",
        json=paid.json()["fields"] | {"id": "x"},
    ).json()
    jana = fresh.done.users["user"][0]
    assert _ids(user, fresh.boldog, uploaded_by=jana) == [mine["id"]]
    assert _ids(user, fresh.boldog, channel="manual") == [mine["id"]]


def test_bulk_actions_report_each_invoice(fresh: Fresh):
    user = fresh.login("user")
    url = f"/api/customers/{fresh.boldog}/invoices"
    booked = make_invoice(fresh.services, fresh.boldog, "anchor-telekom")
    ready = make_invoice(fresh.services, fresh.boldog, "heldout-19-telekom-phone")
    proposal = user.get(f"{url}/{booked}").json()["proposal"]
    user.post(
        f"{url}/{booked}/book",
        json={
            "action": "accepted",
            "coding": {k: proposal[k] for k in ("document", "posting", "budget")},
        },
    )
    recode = user.post(f"{url}/bulk/recode", json={"invoice_ids": [ready, booked, "missing"]})
    assert recode.status_code == 200
    body = recode.json()
    assert (body["done"], body["failed"]) == (1, 2)
    assert [(r["invoice_id"], r["ok"], r["code"]) for r in body["results"]] == [
        (ready, True, None),
        (booked, False, "invalid_state"),
        ("missing", False, "not_found"),
    ]
    pay = user.post(
        f"{url}/bulk/pay", json={"invoice_ids": [booked, ready], "paid_on": "2026-07-03"}
    )
    assert [(r["ok"], r["code"]) for r in pay.json()["results"]] == [
        (True, None),
        (False, "invalid_state"),
    ]
    discard = user.post(
        f"{url}/bulk/discard", json={"invoice_ids": [ready, booked], "reason": "duplicitné"}
    )
    assert [(r["ok"], r["code"]) for r in discard.json()["results"]] == [
        (True, None),
        (False, "invalid_state"),
    ]
    assert user.get(f"{url}/{ready}").json()["state"] == "discarded"
    assert user.post(f"{url}/bulk/discard", json={"invoice_ids": []}).status_code == 422
    viewer = fresh.login("viewer")
    assert viewer.post(f"{url}/bulk/recode", json={"invoice_ids": [ready]}).status_code == 403
