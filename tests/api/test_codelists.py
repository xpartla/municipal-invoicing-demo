"""The codelists API on the seeded database: the knowledge health report (P2-M2-T06)."""

from riso.codelists.domain import HealthCode

BRIDGE_GAPS = ("61", "62", "64")
"""Wages, payroll contributions and transfers: never on a supplier invoice, so no bridge."""


def _ids(seeded):
    return seeded[1].customers


def test_boldogs_health_report_has_only_the_known_gaps(seeded, login):
    boldog = _ids(seeded)["Obec Boldog"]
    response = login("viewer").get(f"/api/customers/{boldog}/health", params={"year": 2026})
    assert response.status_code == 200, response.text
    report = response.json()
    assert (report["year"], report["errors"]) == (2026, 0)
    findings = report["findings"]
    unbridged = [f for f in findings if f["code"] == HealthCode.EK_WITHOUT_BRIDGE]
    assert all(f["subject"][:2] in BRIDGE_GAPS or f["subject"] == "814000" for f in unbridged)
    assert {f["subject"][:2] for f in unbridged} == {"61", "62", "64", "81"}
    assert len(unbridged) == 50 and report["warnings"] == 50
    others = [(f["code"], f["subject"], f["severity"]) for f in findings if f not in unbridged]
    assert others == [("list_missing", "cost_centres", "info")]  # never exported


def test_a_customer_without_lists_is_reported_as_such(seeded, login):
    other = _ids(seeded)["Obec Vzorová Lehota"]
    report = login("staff").get(f"/api/customers/{other}/health", params={"year": 2026}).json()
    missing = {f["subject"] for f in report["findings"] if f["code"] == "list_missing"}
    assert {"accounts", "budget_expense", "document_series"} <= missing
    assert report["errors"] == 3


def test_a_year_without_knowledge_or_lists(seeded, login):
    boldog = _ids(seeded)["Obec Boldog"]
    report = login("user").get(f"/api/customers/{boldog}/health", params={"year": 2027}).json()
    codes = {f["code"] for f in report["findings"]}
    assert {"knowledge_missing", "list_missing", "global_list_missing"} <= codes


def test_the_year_defaults_to_this_year_and_is_bounded(seeded, login):
    boldog = _ids(seeded)["Obec Boldog"]
    client = login("user")
    assert client.get(f"/api/customers/{boldog}/health").status_code == 200
    assert client.get(f"/api/customers/{boldog}/health", params={"year": 1999}).status_code == 422


def test_riso_check_customer_prints_the_report(seeded, monkeypatch, capsys):
    from riso.cli import main

    monkeypatch.setenv("RISO_VAR_DIR", str(seeded[2]))
    monkeypatch.delenv("RISO_DB_URL", raising=False)
    assert main(["check", "--customer", "00305863"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Obec Boldog (00305863), 2026")
    assert "warning  ek_without_bridge: 611000 ×8" in out
    assert out.rstrip().endswith("0 errors, 50 warnings, 1 notes")
    assert main(["check", "--customer", "99900017"]) == 1  # Vzorová Lehota has no lists
    assert main(["check", "--customer", "11111119"]) == 2  # no such customer
