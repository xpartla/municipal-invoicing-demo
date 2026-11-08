"""The code list API (P2-M2-T07) on the seeded database: search on folded text, paging, the
version history and difference, row edits making versions, the global lists' checklist, and
the parameters and conventions. The tests run in order on one seeded database."""

from urllib.parse import quote

from riso.knowledge import load_conventions


def _boldog(seeded):
    return seeded[1].customers["Obec Boldog"]


def _base(seeded, kind):
    return f"/api/customers/{_boldog(seeded)}/codelists/{kind}"


def test_the_overview_lists_every_customer_list(seeded, login):
    found = login("viewer").get(f"/api/customers/{_boldog(seeded)}/codelists?year=2026").json()
    by_kind = {item["kind"]: item for item in found["lists"]}
    assert list(by_kind) == [
        "accounts",
        "budget_expense",
        "budget_income",
        "document_series",
        "transfers",
        "cost_centres",
    ]
    assert by_kind["cost_centres"]["version"] is None
    assert by_kind["budget_expense"]["version"]["entry_count"] == 456
    assert by_kind["budget_expense"]["fields"][:5] == [
        "ek",
        "zdroj",
        "oddiel",
        "trieda",
        "analytika",
    ]
    assert found["years"] == [2026]


def test_search_ignores_case_and_diacritics(seeded, login):
    client = login("viewer")
    url = f"{_base(seeded, 'budget_expense')}/entries"
    plain = client.get(url, params={"year": 2026, "q": "telefon"}).json()
    accented = client.get(url, params={"year": 2026, "q": "TELEFÓN"}).json()
    assert plain["total"] == accented["total"] > 0
    assert any(item["key"].startswith("632005") for item in plain["items"])
    assert [i["key"] for i in plain["items"]] == [i["key"] for i in accented["items"]]
    by_key = client.get(url, params={"year": 2026, "q": "632005 41"}).json()
    assert by_key["total"] >= 1 and all("632005 41" in i["key"] for i in by_key["items"])


def test_entries_come_in_pages_in_the_lists_order(seeded, login):
    client = login("viewer")
    url = f"{_base(seeded, 'accounts')}/entries"
    first = client.get(url, params={"year": 2026, "size": 10}).json()
    second = client.get(url, params={"year": 2026, "size": 10, "page": 2}).json()
    assert first["total"] == second["total"] == 435
    assert [i["key"] for i in first["items"]][:2] == ["012 000", "013 000"]
    assert {i["key"] for i in first["items"]}.isdisjoint(i["key"] for i in second["items"])
    assert client.get(url, params={"size": 201}).status_code == 422


def test_a_global_kind_is_not_a_customer_list(seeded, login):
    response = login("viewer").get(f"{_base(seeded, 'ek')}/entries", params={"year": 2026})
    assert response.status_code == 404


def _active(client, seeded, kind):
    return client.get(f"/api/customers/{_boldog(seeded)}/codelists?year=2026").json()["lists"][
        [
            "accounts",
            "budget_expense",
            "budget_income",
            "document_series",
            "transfers",
            "cost_centres",
        ].index(kind)
    ]["version"]["id"]


def test_an_edit_makes_a_version_and_the_old_one_stays_in_the_history(seeded, login):
    client = login("user")
    first = _active(client, seeded, "accounts")
    response = client.put(
        f"{_base(seeded, 'accounts')}/entries/{quote('518 003')}?year=2026",
        json={"version_id": first, "values": {"description": "Telekomunikácie a pošta"}},
    )
    assert response.status_code == 200, response.text
    second = response.json()
    assert (second["number"], second["origin"], second["status"]) == (2, "edit", "active")
    history = client.get(f"{_base(seeded, 'accounts')}/versions?year=2026").json()
    assert [(v["number"], v["status"]) for v in history] == [(2, "active"), (1, "superseded")]
    old = client.get(
        f"{_base(seeded, 'accounts')}/entries", params={"version": first, "q": "518 003"}
    ).json()
    assert old["items"][0]["values"]["description"] != "Telekomunikácie a pošta"
    diff = client.get(
        f"{_base(seeded, 'accounts')}/diff", params={"old": first, "new": second["id"]}
    ).json()
    assert diff["added"] == [] and diff["removed"] == []
    [change] = diff["changed"]
    assert change["key"] == "518 003"
    assert change["after"]["values"]["description"] == "Telekomunikácie a pošta"
    assert change["after"]["values"]["row"] == change["before"]["values"]["row"]  # kept


def test_the_edit_is_audited_with_before_and_after(seeded, login):
    entries = (
        login("admin")
        .get("/api/admin/audit", params={"action": "codelists.entry_edited"})
        .json()["items"]
    )
    [entry] = entries
    assert entry["customer_id"] == _boldog(seeded)
    assert entry["details"]["key"] == "518 003" and entry["details"]["number"] == 2
    assert entry["details"]["after"]["description"] == "Telekomunikácie a pošta"


def test_adding_deactivating_and_reactivating_rows(seeded, login):
    client = login("staff")
    url = f"{_base(seeded, 'accounts')}/entries"
    current = _active(client, seeded, "accounts")
    added = client.post(
        f"{url}?year=2026",
        json={"version_id": current, "values": {"su": "518", "au": "099", "type": "cost"}},
    )
    assert added.status_code == 201 and added.json()["number"] == 3
    gone = client.post(
        f"{url}/{quote('518 099')}/deactivate?year=2026", json={"version_id": added.json()["id"]}
    )
    assert gone.status_code == 200 and gone.json()["number"] == 4
    inactive = client.get(url, params={"year": 2026, "active": "false"}).json()
    assert [i["key"] for i in inactive["items"]] == ["518 099"]
    back = client.post(
        f"{url}/{quote('518 099')}/reactivate?year=2026", json={"version_id": gone.json()["id"]}
    )
    assert back.status_code == 200 and back.json()["number"] == 5


def test_a_stale_version_a_used_key_and_a_bad_row_are_refused(seeded, login):
    client = login("user")
    url = f"{_base(seeded, 'accounts')}/entries"
    current = _active(client, seeded, "accounts")
    row = {"su": "518", "au": "098", "type": "cost"}
    stale = client.post(f"{url}?year=2026", json={"version_id": "0" * 36, "values": row})
    assert stale.status_code == 409
    used = client.post(
        f"{url}?year=2026", json={"version_id": current, "values": {**row, "au": "003"}}
    )
    assert used.status_code == 409
    bad = client.post(
        f"{url}?year=2026", json={"version_id": current, "values": {**row, "su": "5"}}
    )
    assert bad.status_code == 422
    assert bad.json()["detail"][0]["loc"] == ["body", "values", "su"]


def test_a_viewer_may_not_edit(seeded, login):
    client = login("viewer")
    current = _active(client, seeded, "accounts")
    response = client.post(
        f"{_base(seeded, 'accounts')}/entries/{quote('518 003')}/deactivate?year=2026",
        json={"version_id": current},
    )
    assert response.status_code == 403


def test_the_global_checklist_and_lists(seeded, login):
    admin = login("admin")
    checklist = admin.get("/api/admin/codelists").json()
    by_year = {y["year"]: y for y in checklist}
    assert by_year[2026]["complete"] is True
    assert [s["version"]["entry_count"] for s in by_year[2026]["lists"]] == [691, 216, 285, 316]
    assert by_year[2027]["complete"] is False
    found = admin.get(
        "/api/admin/codelists/ek/entries", params={"year": 2026, "q": "telekomunikacne"}
    ).json()
    assert "632005" in [i["key"] for i in found["items"]]
    versions = admin.get("/api/admin/codelists/cofog/versions", params={"year": 2026}).json()
    assert [v["number"] for v in versions] == [1]
    assert admin.get("/api/admin/codelists/accounts/entries").status_code == 404
    assert login("staff").get("/api/admin/codelists").status_code == 403


def test_parameters_read_and_write(seeded, login):
    url = f"/api/customers/{_boldog(seeded)}/parameters"
    client = login("user")
    values = client.get(url, params={"year": 2026}).json()["values"]
    assert values["default_series"] == "FD" and "reference_period" not in values
    bad = client.put(url, params={"year": 2026}, json={"values": {**values, "default_dal": "321"}})
    assert bad.status_code == 422
    assert bad.json()["detail"][0]["loc"] == ["body", "values", "default_dal"]
    ok = client.put(url, params={"year": 2026}, json={"values": {**values, "vat_payer": True}})
    assert ok.status_code == 200 and ok.json()["values"]["vat_payer"] is True
    client.put(url, params={"year": 2026}, json={"values": values})
    assert client.get(url, params={"year": 2027}).status_code == 404
    assert (
        login("viewer").put(url, params={"year": 2026}, json={"values": values}).status_code == 403
    )


def test_conventions_read_and_write_with_the_revision(seeded, login):
    url = f"/api/customers/{_boldog(seeded)}/conventions"
    client = login("user")
    current = client.get(url, params={"year": 2026}).json()
    assert current["revision"] == 1
    assert current["document"]["canteen"]["md"] == "501 080"
    document = load_conventions("00305863", 2026).model_dump(mode="json")
    document["au_rules"]["debit"]["518"]["rules"][0]["au"] = "001"
    saved = client.put(url, params={"year": 2026}, json={"revision": 1, "document": document})
    assert saved.status_code == 200 and saved.json()["revision"] == 2
    stale = client.put(url, params={"year": 2026}, json={"revision": 1, "document": document})
    assert stale.status_code == 409
    bad = client.put(
        url, params={"year": 2026}, json={"revision": 2, "document": {"canteen": {"md": "x"}}}
    )
    assert bad.status_code == 422
    assert bad.json()["detail"][0]["loc"][:3] == ["body", "document", "canteen"]
    restored = load_conventions("00305863", 2026).model_dump(mode="json")
    assert (
        client.put(url, params={"year": 2026}, json={"revision": 2, "document": restored}).json()[
            "revision"
        ]
        == 3
    )
