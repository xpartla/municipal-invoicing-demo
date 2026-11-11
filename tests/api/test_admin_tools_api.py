"""The admin tools' API (P2-M7-T05, plan §10.9, decision 67): Úlohy (the list, retry of a
failed job, cancel of a queued one, both audited), the customer data export (every table's
rows of the customer and none of another's, its members without credentials, its files),
and Vyhodnotenie and the stateless coding behind the admin's permission."""

import io
import json
import zipfile
from datetime import timedelta

import pytest
from sqlalchemy import select

from riso.jobs.domain import Job, RetryPolicy
from riso.jobs.infrastructure.repository import SqlJobRepository
from riso.platform.db import metadata
from tests.api.conftest import Fresh


def _job(fresh: Fresh, job_id: str, *, status: str, customer_id: str | None = None) -> None:
    services = fresh.services
    with services.uow() as uow:
        now = uow.clock.now()
        job = Job.new(job_id, "noop", {}, now, max_attempts=1, customer_id=customer_id)
        if status in ("failed", "running"):
            job.claim(now, "w", timedelta(minutes=1))
        if status == "failed":
            job.fail(now, "boom", RetryPolicy())
        SqlJobRepository(uow.session).add(job)
        uow.commit()


def test_the_jobs_list_filters_and_pages(fresh):
    _job(fresh, "job-failed", status="failed", customer_id=fresh.boldog)
    _job(fresh, "job-queued", status="queued")
    admin = fresh.login("admin")
    body = admin.get("/api/admin/jobs").json()
    ids = [j["id"] for j in body["items"]]
    assert {"job-failed", "job-queued"} <= set(ids)
    assert body["total"] == len(ids) and "noop" in body["kinds"]
    failed = admin.get("/api/admin/jobs", params={"status": "failed"}).json()
    assert [j["id"] for j in failed["items"]] == ["job-failed"]
    assert failed["items"][0]["last_error"] == "boom"
    assert failed["items"][0]["customer_id"] == fresh.boldog
    by_kind = admin.get("/api/admin/jobs", params={"kind": "noop", "size": 1}).json()
    assert by_kind["total"] == 2 and len(by_kind["items"]) == 1


def test_a_failed_job_is_retried_and_a_queued_one_cancelled_both_audited(fresh):
    _job(fresh, "job-failed", status="failed", customer_id=fresh.boldog)
    _job(fresh, "job-queued", status="queued")
    admin = fresh.login("admin")
    retried = admin.post("/api/admin/jobs/job-failed/retry")
    assert retried.status_code == 200, retried.text
    assert (retried.json()["status"], retried.json()["attempts"]) == ("queued", 0)
    cancelled = admin.post("/api/admin/jobs/job-queued/cancel")
    assert cancelled.json()["status"] == "cancelled"
    # Retrying a queued job and cancelling a cancelled one are refused.
    assert admin.post("/api/admin/jobs/job-failed/retry").status_code == 409
    assert admin.post("/api/admin/jobs/job-queued/cancel").status_code == 409
    assert admin.post("/api/admin/jobs/nothing/retry").status_code == 404
    events = admin.get("/api/admin/audit", params={"action": "job."}).json()["items"]
    assert [(e["action"], e["target_id"]) for e in events] == [
        ("job.cancelled", "job-queued"),
        ("job.retried", "job-failed"),
    ]
    assert events[1]["customer_id"] == fresh.boldog


@pytest.mark.parametrize("key", ["staff", "user", "viewer"])
def test_only_admins_reach_the_tools(fresh, key):
    client = fresh.login(key)
    assert client.get("/api/admin/jobs").status_code == 403
    assert client.get("/api/admin/eval").status_code == 403
    assert client.post(f"/api/admin/customers/{fresh.boldog}/data-export").status_code == 403


def _export(fresh: Fresh, customer_id: str) -> tuple[dict, zipfile.ZipFile]:
    admin = fresh.login("admin")
    started = admin.post(f"/api/admin/customers/{customer_id}/data-export")
    assert started.status_code == 200, started.text
    job_id = started.json()["id"]
    assert fresh.services.worker().run_pending() >= 1
    job = next(j for j in admin.get("/api/admin/jobs").json()["items"] if j["id"] == job_id)
    assert job["status"] == "succeeded", job
    download = admin.get(f"/api/admin/jobs/{job_id}/file")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert "attachment" in download.headers["content-disposition"]
    return job, zipfile.ZipFile(io.BytesIO(download.content))


def test_the_data_export_holds_every_table_of_the_customer_and_nothing_of_another(fresh):
    job, archive = _export(fresh, fresh.boldog)
    names = set(archive.namelist())
    with fresh.services.uow(immediate=False) as uow:
        s = uow.session
        customer_tables = [t for t in metadata.tables.values() if "customer_id" in t.columns]
        assert len(customer_tables) > 20
        for table in customer_tables:
            exported = json.loads(archive.read(f"tables/{table.name}.json"))
            where = [table.c.customer_id == fresh.boldog]
            if table.name == "audit_events":  # the export's own entry follows the dump
                where.append(table.c.action != "customer.data_exported")
            mine = s.execute(select(table).where(*where)).all()
            assert len(exported) == len(mine), table.name
            assert {r["customer_id"] for r in exported} <= {fresh.boldog}, table.name
            assert job["result"]["tables"][table.name] == len(mine)
        others = set(fresh.done.customers.values()) - {fresh.boldog}
        text = b"".join(archive.read(n) for n in names if n.startswith("tables/")).decode()
        assert not any(other in text for other in others)
    customers = json.loads(archive.read("tables/customers.json"))
    assert [c["id"] for c in customers] == [fresh.boldog]
    invoices = json.loads(archive.read("tables/invoices.json"))
    assert len(invoices) == 74


def test_the_data_export_has_the_members_without_credentials_and_the_files(fresh):
    uploaded = fresh.login("user").post(
        f"/api/customers/{fresh.boldog}/imports",
        files={"file": ("ucty.csv", b"SU;AU;Nazov\n518;001;Sluzby\n", "text/csv")},
        data={"import_type": "accounts", "year": "2026"},
    )
    assert uploaded.status_code == 201, uploaded.text
    _, archive = _export(fresh, fresh.boldog)
    users = json.loads(archive.read("tables/users.json"))
    emails = {u["email"] for u in users}
    assert {fresh.done.users["user"][1], fresh.done.users["viewer"][1]} == emails
    assert all("password_hash" not in u for u in users)
    assert "argon2" not in archive.read("tables/users.json").decode()
    assert all("body" not in m for m in json.loads(archive.read("tables/mail_outbox.json")))
    runs = json.loads(archive.read("tables/import_runs.json"))
    assert [r["file_name"] for r in runs] == ["ucty.csv"]
    for run in runs:
        assert f"files/{run['file_key']}" in archive.namelist()
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["customer_id"] == fresh.boldog


def test_the_data_export_is_audited_and_works_for_a_deleted_customer(fresh):
    admin = fresh.login("admin")
    second = fresh.done.customers["Obec Vzorová Lehota"]
    assert admin.delete(f"/api/customers/{second}").status_code == 200
    _, archive = _export(fresh, second)
    customers = json.loads(archive.read("tables/customers.json"))
    assert customers[0]["status"] == "deleted"
    actions = [
        e["action"]
        for e in admin.get("/api/admin/audit", params={"customer_id": second}).json()["items"]
    ]
    assert "customer.data_exported" in actions and "customer.data_export_started" in actions
    assert admin.post("/api/admin/customers/nobody/data-export").status_code == 404


def test_only_a_finished_data_export_has_a_file(fresh):
    _job(fresh, "job-other", status="failed")
    admin = fresh.login("admin")
    assert admin.get("/api/admin/jobs/job-other/file").status_code == 404
    assert admin.get("/api/admin/jobs/nothing/file").status_code == 404


def test_the_evaluation_and_the_stateless_coding_need_an_admin(fresh):
    anonymous = fresh.login("admin")
    anonymous.post("/api/auth/logout")
    assert anonymous.get("/api/admin/eval").status_code == 401
    admin = fresh.login("admin")
    report = admin.get("/api/admin/eval", params={"split": "anchor"})
    assert report.status_code == 200, report.text
    assert report.json()["split"] == "anchor" and len(report.json()["cases"]) == 4
    # The demo's public routes are gone.
    assert admin.get("/api/eval").status_code == 404
