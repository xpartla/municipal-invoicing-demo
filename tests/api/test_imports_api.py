"""The import and template API (P2-M3-T07): the whole flow through HTTP as the wizard calls
it: upload, preview with the suggested mapping, mapping, dry run, report, apply (with the
confirmation for errors against the global lists), cancel, history, the file, and the
templates; and a global list's import as the admin."""

import csv
import io

import pytest

from riso.api import Settings, create_app
from riso.api.composition import build_services
from riso.api.seed import seed
from riso.exchange.domain.templates import BOOKINGS_HEADER
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.platform import Settings as PlatformSettings
from tests.api.conftest import SEED_PASSWORD, ApiClient

YEAR = 2026
CHART_HEADER = ["Syntetický účet", "Analytický účet", "Druh účtu", "Názov"]


@pytest.fixture
def env(tmp_path):
    settings = PlatformSettings(var_dir=tmp_path / "var", env="test")
    done = seed(settings, password=SEED_PASSWORD, hasher=Argon2Hasher.fast())
    services = build_services(settings, hasher=Argon2Hasher.fast())
    app = create_app(
        Settings(var_dir=settings.var_dir, platform=settings, run_worker=False), services=services
    )

    def login(key):
        client = ApiClient(app)
        client.login(done.users[key][1], SEED_PASSWORD)
        return client

    yield services, done, login
    services.close()


def _csv(rows, delimiter=";", encoding="windows-1250") -> bytes:
    out = io.StringIO()
    csv.writer(out, delimiter=delimiter, lineterminator="\r\n").writerows(rows)
    return out.getvalue().encode(encoding)


def _chart(*extra):
    return _csv(
        [
            CHART_HEADER,
            ["518", "1", "Nákladový", "Telefóny"],
            ["518", "2", "Nákladový", "Internet"],
            ["321", "0", "Pasívny", "Dodávatelia"],
            *extra,
        ]
    )


def _upload(client, customer_id, data, import_type="accounts", name="rozvrh.csv"):
    return client.post(
        f"/api/customers/{customer_id}/imports",
        files={"file": (name, data, "text/csv")},
        data={"import_type": import_type, "year": str(YEAR)},
    )


def _dry_run(client, services, base):
    response = client.post(f"{base}/dry-run")
    assert response.status_code == 202, response.text
    assert response.json()["job_id"]
    services.worker().run_pending()
    return client.get(base).json()


def _mapped(client, base, preview):
    response = client.put(
        f"{base}/mapping",
        json={
            "options": {"header_row": preview["header_row"], "delimiter": preview["delimiter"]},
            "mapping": preview["suggestion"],
            "template_id": preview["template_id"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_whole_flow_through_http(env):
    services, done, login = env
    jana = login("user")
    boldog = done.customers["Obec Boldog"]
    uploaded = _upload(jana, boldog, _chart())
    assert uploaded.status_code == 201, uploaded.text
    run = uploaded.json()
    assert (run["state"], run["file"]["format"], run["file"]["name"]) == (
        "uploaded",
        "csv",
        "rozvrh.csv",
    )
    base = f"/api/customers/{boldog}/imports/{run['id']}"

    preview = jana.get(f"{base}/preview").json()
    assert (preview["format"], preview["encoding"], preview["delimiter"]) == (
        "csv",
        "windows-1250",
        ";",
    )
    assert [c["header"] for c in preview["columns"]] == CHART_HEADER
    assert preview["rows"][0] == {"number": 2, "cells": ["518", "1", "Nákladový", "Telefóny"]}
    assert preview["template_id"] is None
    assert preview["suggestion"]["fields"]["su"]["column"] == "Syntetický účet"
    assert {f["name"]: f["required"] for f in preview["fields"]}["type"] is True
    # The options can be chosen: no header row reads the header as data.
    raw = jana.get(f"{base}/preview", params={"header_row": 0}).json()
    assert raw["header_row"] == 0 and raw["rows"][0]["cells"][0] == "Syntetický účet"

    assert _mapped(jana, base, preview)["state"] == "mapped"
    report = _dry_run(jana, services, base)
    assert report["state"] == "dry_run_ok", report["report"]
    assert report["can_apply"] is True
    assert report["report"]["entries"] == 3 and report["report"]["diff"]["base_number"] == 1
    applied = jana.post(f"{base}/apply", json={})
    assert applied.status_code == 202 and applied.json()["applying"] is True
    services.worker().run_pending()
    done_run = jana.get(base).json()
    assert done_run["state"] == "applied" and done_run["version_id"]
    lists = jana.get(f"/api/customers/{boldog}/codelists/accounts/versions", params={"year": YEAR})
    assert lists.status_code == 200, lists.text
    assert lists.json()[0]["id"] == done_run["version_id"]

    # Save the mapping as the customer's template; the next upload gets it.
    saved = jana.post(f"{base}/template", json={"scope": "customer", "name": "Rozvrh – vlastný"})
    assert saved.status_code == 201, saved.text
    template = saved.json()
    assert (template["scope"], template["owner_id"]) == ("customer", boldog)
    second = _upload(jana, boldog, _chart()).json()
    again = jana.get(f"/api/customers/{boldog}/imports/{second['id']}/preview").json()
    assert (again["template_id"], again["template_name"]) == (template["id"], "Rozvrh – vlastný")

    history = jana.get(f"/api/customers/{boldog}/imports").json()
    assert history["total"] == 2
    assert [r["state"] for r in history["items"]] == ["uploaded", "applied"]
    cancelled = jana.post(f"/api/customers/{boldog}/imports/{second['id']}/cancel")
    assert cancelled.json()["state"] == "cancelled"
    file = jana.get(f"{base}/file")
    assert file.status_code == 200 and file.content == _chart()
    assert "rozvrh.csv" in file.headers["content-disposition"]

    listed = jana.get(f"/api/customers/{boldog}/templates", params={"import_type": "accounts"})
    assert [t["id"] for t in listed.json()][:1] == [template["id"]]
    renamed = jana.put(
        f"/api/customers/{boldog}/templates/{template['id']}",
        json={
            "name": "Rozvrh 2026",
            "signature": template["signature"],
            "mapping": template["mapping"],
        },
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "Rozvrh 2026"
    assert jana.delete(f"/api/customers/{boldog}/templates/{template['id']}").status_code == 204
    builtin = jana.delete(f"/api/customers/{boldog}/templates/builtin:topset-chart")
    assert builtin.status_code == 409  # built-in templates are read-only


def test_a_failing_import_cannot_be_applied(env):
    services, done, login = env
    jana = login("user")
    boldog = done.customers["Obec Boldog"]
    run = _upload(jana, boldog, _chart(["5x8", "3", "Nákladový", "zlý"])).json()
    base = f"/api/customers/{boldog}/imports/{run['id']}"
    _mapped(jana, base, jana.get(f"{base}/preview").json())
    report = _dry_run(jana, services, base)
    assert report["state"] == "dry_run_failed" and report["can_apply"] is False
    errors = report["report"]["errors"]
    assert errors and errors[0]["rows"] == [5] and not errors[0]["confirmable"]
    for body in ({}, {"confirm_errors": True}):
        refused = jana.post(f"{base}/apply", json=body)
        assert refused.status_code == 409, refused.text


def test_errors_against_the_global_lists_need_the_confirmation(env):
    services, done, login = env
    jana = login("user")
    boldog = done.customers["Obec Boldog"]
    rows = [
        ["EK", "Zdroj", "Oddiel", "Trieda", "Analytika", "Popis"],
        ["632001", "41", "01", "110", "000", "Energie"],
        ["999999", "41", "01", "110", "000", "Neznáma položka"],
    ]
    run = _upload(jana, boldog, _csv(rows), import_type="budget_expense").json()
    base = f"/api/customers/{boldog}/imports/{run['id']}"
    _mapped(jana, base, jana.get(f"{base}/preview").json())
    report = _dry_run(jana, services, base)
    assert report["state"] == "dry_run_failed" and report["can_apply"] is True
    assert {(e["code"], e["confirmable"]) for e in report["report"]["errors"]} == {
        ("unknown_ek", True)
    }
    assert jana.post(f"{base}/apply", json={}).status_code == 409
    confirmed = jana.post(f"{base}/apply", json={"confirm_errors": True})
    assert confirmed.status_code == 202 and confirmed.json()["errors_confirmed"] is True
    services.worker().run_pending()
    assert jana.get(base).json()["state"] == "applied"


def test_bad_uploads_are_refused(env):
    _, done, login = env
    jana = login("user")
    boldog = done.customers["Obec Boldog"]
    assert _upload(jana, boldog, b"").status_code == 422
    assert _upload(jana, boldog, _chart(), import_type="ek").status_code == 422  # global
    assert _upload(jana, boldog, _chart(), import_type="nothing").status_code == 422
    viewer = login("viewer")
    assert _upload(viewer, boldog, _chart()).status_code == 403
    assert viewer.get(f"/api/customers/{boldog}/imports").status_code == 200
    assert viewer.get(f"/api/customers/{boldog}/templates").status_code == 403


def test_a_global_list_imports_as_the_admin(env):
    services, _, login = env
    admin = login("admin")
    data = _csv([["code", "name"], ["611000", "Tarifný plat"], ["632001", "Energie"]], ",", "utf-8")
    uploaded = admin.post(
        "/api/admin/imports",
        files={"file": ("ek.csv", data, "text/csv")},
        data={"import_type": "ek", "year": "2027"},
    )
    assert uploaded.status_code == 201, uploaded.text
    base = f"/api/admin/imports/{uploaded.json()['id']}"
    preview = admin.get(f"{base}/preview").json()
    assert preview["template_id"] == "builtin:global-ek"
    _mapped(admin, base, preview)
    assert _dry_run(admin, services, base)["state"] == "dry_run_ok"
    admin.post(f"{base}/apply", json={})
    services.worker().run_pending()
    assert admin.get(base).json()["state"] == "applied"
    assert admin.get("/api/admin/imports").json()["total"] >= 1
    templates = admin.get("/api/admin/templates", params={"import_type": "ek"}).json()
    assert [t["id"] for t in templates] == ["builtin:global-ek"]
    saved = admin.post(f"{base}/template", json={"scope": "global", "name": "EK – CSV"})
    assert saved.status_code == 201 and saved.json()["owner_id"] is None
    assert admin.delete(f"/api/admin/templates/{saved.json()['id']}").status_code == 204


def test_past_bookings_import_through_http(env):
    services, done, login = env
    jana = login("user")
    boldog = done.customers["Obec Boldog"]
    book = _csv(
        [
            list(BOOKINGS_HEADER),
            [
                "11223341",
                "Tomáš Ukážkový",
                "FD/090/26",
                "28.4.2026",
                "812,50",
                "2026041",
                "635006 41 06 200 000",
                "511 000",
                "321 000",
                "zeleň",
                "kosenie 4/2026",
            ],
        ]  # fmt: skip
    )
    run = _upload(jana, boldog, book, import_type="past_bookings", name="kniha.csv").json()
    base = f"/api/customers/{boldog}/imports/{run['id']}"
    preview = jana.get(f"{base}/preview").json()
    assert preview["template_id"] == "builtin:generic-bookings"
    assert {f["name"] for f in preview["fields"] if f["line"]} == {
        "budget_key", "md", "dal", "budget_text", "posting_text",
    }  # fmt: skip
    _mapped(jana, base, preview)
    report = _dry_run(jana, services, base)
    assert report["state"] == "dry_run_ok", report["report"]["errors"]
    assert report["report"]["numbers_used"] == 1
    jana.post(f"{base}/apply", json={})
    services.worker().run_pending()
    applied = jana.get(base).json()
    assert applied["state"] == "applied" and applied["version_id"] is None


def test_templates_per_scope(env):
    services, done, login = env
    jana, staff = login("user"), login("staff")
    boldog = done.customers["Obec Boldog"]
    run = _upload(jana, boldog, _chart()).json()
    base = f"/api/customers/{boldog}/imports/{run['id']}"
    _mapped(jana, base, jana.get(f"{base}/preview").json())
    for scope in ("provider", "global"):
        refused = jana.post(f"{base}/template", json={"scope": scope, "name": "Vzor"})
        assert refused.status_code == 403, (scope, refused.text)
    saved = staff.post(f"{base}/template", json={"scope": "provider", "name": "Vzor – rozvrh"})
    assert saved.status_code == 201, saved.text
    assert saved.json()["owner_id"] == done.provider_id
    assert (
        staff.post(f"{base}/template", json={"scope": "customer", "name": "x"}).status_code == 403
    )
    template_id = saved.json()["id"]
    # Jana uses the provider's template but cannot remove it; staff can.
    listed = jana.get(f"/api/customers/{boldog}/templates").json()
    assert template_id in {t["id"] for t in listed}
    assert jana.delete(f"/api/customers/{boldog}/templates/{template_id}").status_code == 403
    assert staff.delete(f"/api/customers/{boldog}/templates/{template_id}").status_code == 204
