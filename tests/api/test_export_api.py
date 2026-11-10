"""Exporting booked invoices through the API (P2-M4-T06): the preview with the "already
exported" notice, the run and its job, the file kept in storage, the invoices marked exported
(paid ones stay paid) and their numbers frozen."""

import io

from openpyxl import load_workbook

from tests.api.conftest import Fresh
from tests.factories import make_invoice


def _book(fresh: Fresh, client, case_id: str) -> str:
    invoice_id = make_invoice(fresh.services, fresh.boldog, case_id)
    url = f"/api/customers/{fresh.boldog}/invoices/{invoice_id}"
    proposal = client.get(url).json()["proposal"]
    coding = {k: proposal[k] for k in ("document", "posting", "budget")}
    booked = client.post(f"{url}/book", json={"action": "corrected", "coding": coding})
    assert booked.status_code == 200, booked.text
    return invoice_id


def _export(fresh: Fresh, client, body: dict) -> dict:
    url = f"/api/customers/{fresh.boldog}/exports"
    started = client.post(url, json=body)
    assert started.status_code == 202, started.text
    run = started.json()
    assert run["state"] == "queued" and run["job_id"]
    fresh.services.worker().run_pending()
    done = client.get(f"{url}/{run['id']}").json()
    assert done["state"] == "done", done
    return done


def test_an_export_writes_the_file_and_marks_the_invoices(fresh: Fresh):
    user = fresh.login("user")
    split = _book(fresh, user, "seed-16-spp-gas-ocu-kd")
    single = _book(fresh, user, "anchor-telekom")
    ready = make_invoice(fresh.services, fresh.boldog, "heldout-19-telekom-phone")
    body = {"invoice_ids": [split, single, ready]}
    url = f"/api/customers/{fresh.boldog}/exports"
    preview = user.post(f"{url}/preview", json=body)
    assert preview.json() == {"invoices": 2, "again": 0, "skipped": 1}
    run = _export(fresh, user, body)
    assert (run["requested"], run["invoices"], run["rows"], run["again"]) == (2, 2, 3, 0)
    assert run["file_name"].startswith("faktury-") and run["file_name"].endswith(".csv")
    assert run["scope"] == {"invoice_ids": [split, single, ready]}

    file = user.get(f"{url}/{run['id']}/file")
    assert file.status_code == 200
    assert file.headers["content-type"].startswith("text/csv")
    assert "attachment" in file.headers["content-disposition"]
    lines = file.content.decode("utf-8-sig").split("\r\n")
    assert lines[0].startswith("Rad;Číslo dokladu;")
    assert len([line for line in lines[1:] if line]) == 3  # the split invoice gives two rows
    assert any(";FD/144/26;23.06.2026;" in line for line in lines)

    invoices = f"/api/customers/{fresh.boldog}/invoices"
    for invoice_id in (split, single):
        detail = user.get(f"{invoices}/{invoice_id}").json()
        assert detail["state"] == "exported" and detail["exported_at"] is not None
    assert user.get(f"{invoices}/{ready}").json()["state"] == "ready"
    history = user.get(f"{invoices}/{single}/history").json()["items"]
    assert history[-1]["kind"] == "exported"
    assert history[-1]["details"] == {"export_run_id": run["id"], "again": False}
    series = user.get(f"/api/customers/{fresh.boldog}/number-series?year=2026").json()
    fd = next(s for s in series["items"] if s["series"] == "FD")
    held = {u["number"]: u for u in fd["used"]}
    assert held["FD/144/26"]["frozen"] is True


def test_exporting_again_says_so_and_a_paid_invoice_stays_paid(fresh: Fresh):
    user = fresh.login("user")
    first = _book(fresh, user, "anchor-telekom")
    _export(fresh, user, {"invoice_ids": [first]})
    paid = _book(fresh, user, "heldout-19-telekom-phone")
    pay = user.post(
        f"/api/customers/{fresh.boldog}/invoices/{paid}/pay", json={"paid_on": "2026-07-01"}
    )
    assert pay.status_code == 200
    body = {"filter": {"state": ["exported", "paid"]}, "format": "xlsx"}
    preview = user.post(f"/api/customers/{fresh.boldog}/exports/preview", json=body)
    assert preview.json() == {"invoices": 2, "again": 1, "skipped": 0}
    run = _export(fresh, user, body)
    assert (run["invoices"], run["again"], run["format"]) == (2, 1, "xlsx")
    assert run["scope"] == {"filter": {"state": ["exported", "paid"]}, "sort": "booking_date"}
    file = user.get(f"/api/customers/{fresh.boldog}/exports/{run['id']}/file")
    sheet = load_workbook(io.BytesIO(file.content))["Faktúry"]
    numbers = [r[1] for r in sheet.iter_rows(min_row=2, values_only=True)]
    assert numbers == ["FD/144/26", "FD/252/26"]  # by booking date
    invoices = f"/api/customers/{fresh.boldog}/invoices"
    assert user.get(f"{invoices}/{paid}").json()["state"] == "paid"
    assert user.get(f"{invoices}/{paid}").json()["exported_at"] is not None
    assert user.get(f"{invoices}/{first}").json()["state"] == "exported"


def test_the_export_history_and_who_may_export(fresh: Fresh):
    user, viewer = fresh.login("user"), fresh.login("viewer")
    booked = _book(fresh, user, "anchor-telekom")
    url = f"/api/customers/{fresh.boldog}/exports"
    assert viewer.post(url, json={"invoice_ids": [booked]}).status_code == 403
    first = _export(fresh, user, {"invoice_ids": [booked]})
    second = _export(fresh, user, {"invoice_ids": [booked]})
    history = viewer.get(url).json()
    assert history["total"] == 2
    assert [r["id"] for r in history["items"]] == [second["id"], first["id"]]
    assert viewer.get(f"{url}/{first['id']}/file").status_code == 200


def test_nothing_booked_is_nothing_to_export(fresh: Fresh):
    user = fresh.login("user")
    ready = make_invoice(fresh.services, fresh.boldog, "anchor-telekom")
    url = f"/api/customers/{fresh.boldog}/exports"
    refused = user.post(url, json={"invoice_ids": [ready]})
    assert refused.status_code == 422 and refused.json()["detail"][0]["type"] == "nothing"
    assert user.post(url, json={"sort": "-nonsense"}).status_code == 422
    assert user.get(url).json()["total"] == 0


def test_a_run_whose_invoices_were_unbooked_fails_without_a_file(fresh: Fresh):
    user = fresh.login("user")
    booked = _book(fresh, user, "anchor-telekom")
    url = f"/api/customers/{fresh.boldog}/exports"
    run = user.post(url, json={"invoice_ids": [booked]}).json()
    unbooked = user.post(f"/api/customers/{fresh.boldog}/invoices/{booked}/unbook", json={})
    assert unbooked.status_code == 200
    fresh.services.worker().run_pending()
    failed = user.get(f"{url}/{run['id']}").json()
    assert failed["state"] == "failed" and failed["file_name"] is None
    assert user.get(f"{url}/{run['id']}/file").status_code == 404
