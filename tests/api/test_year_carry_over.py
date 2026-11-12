"""Starting a customer's new year from the previous one (plan §6.6, P2-M8-T08): the code lists,
parameters and conventions the new year lacks, copied from the previous year; what it has
stays; the number series are not copied; another customer is untouched; the permission; and
a refusal when there is nothing to take."""

CUSTOMER_LISTS = {
    "accounts",
    "budget_expense",
    "budget_income",
    "cost_centres",
    "document_series",
    "transfers",
}


def _lists(client, customer_id: str, year: int) -> dict[str, dict | None]:
    body = client.get(f"/api/customers/{customer_id}/codelists", params={"year": year}).json()
    return {item["kind"]: item["version"] for item in body["lists"]}


def test_a_new_year_takes_the_previous_years_lists_parameters_and_conventions(fresh):
    user = fresh.login("user")
    boldog = fresh.boldog
    before = _lists(user, boldog, 2026)
    assert all(before[kind] for kind in CUSTOMER_LISTS - {"cost_centres"})
    assert all(v is None for v in _lists(user, boldog, 2027).values())

    response = user.post(f"/api/customers/{boldog}/years/2027/carry-over")
    assert response.status_code == 200, response.text
    done = response.json()
    assert done["year"] == 2027 and done["from_year"] == 2026
    assert done["parameters"] is True and done["conventions"] is True
    assert set(done["code_lists"]) == {k for k, v in before.items() if v is not None}

    after = _lists(user, boldog, 2027)
    for kind in done["code_lists"]:
        assert after[kind]["number"] == 1 and after[kind]["origin"] == "copy"
        assert after[kind]["entry_count"] == before[kind]["entry_count"]
    parameters = user.get(f"/api/customers/{boldog}/parameters", params={"year": 2027}).json()
    old = user.get(f"/api/customers/{boldog}/parameters", params={"year": 2026}).json()
    assert parameters["year"] == 2027 and parameters["values"] == old["values"]
    conventions = user.get(f"/api/customers/{boldog}/conventions", params={"year": 2027}).json()
    assert conventions["revision"] == 1
    # The number series start afresh (§6.6).
    series = user.get(f"/api/customers/{boldog}/number-series", params={"year": 2027}).json()
    assert all(s["last_used"] == 0 for s in series["items"])
    # Audited.
    admin = fresh.login("admin")
    audit = admin.get(
        "/api/admin/audit", params={"action": "codelists.year_carried_over", "customer": boldog}
    ).json()
    assert audit["total"] == 1

    # Nothing more to take: refused.
    again = user.post(f"/api/customers/{boldog}/years/2027/carry-over")
    assert again.status_code == 409


def test_what_the_new_year_has_stays(fresh):
    user = fresh.login("user")
    boldog = fresh.boldog
    # 2027 gets its own parameters first; the carry-over leaves them and takes the rest.
    current = user.get(f"/api/customers/{boldog}/parameters", params={"year": 2026}).json()
    own = current["values"] | {"default_zdroj": "46"}
    saved = user.put(
        f"/api/customers/{boldog}/parameters", params={"year": 2027}, json={"values": own}
    )
    assert saved.status_code == 200, saved.text
    done = user.post(f"/api/customers/{boldog}/years/2027/carry-over").json()
    assert done["parameters"] is False and done["code_lists"]
    kept = user.get(f"/api/customers/{boldog}/parameters", params={"year": 2027}).json()
    assert kept["values"]["default_zdroj"] == "46"


def test_only_editors_of_the_customer_carry_a_year_over(fresh):
    boldog = fresh.boldog
    viewer = fresh.login("viewer")
    assert viewer.post(f"/api/customers/{boldog}/years/2027/carry-over").status_code == 403
    staff = fresh.login("staff")
    unassigned = fresh.done.customers["Obec Nezávislá"]
    assert staff.post(f"/api/customers/{unassigned}/years/2027/carry-over").status_code == 404
    # A year without a previous one to take from is refused, and so is an impossible year.
    user = fresh.login("user")
    assert user.post(f"/api/customers/{boldog}/years/2026/carry-over").status_code == 409
    assert user.post(f"/api/customers/{boldog}/years/1999/carry-over").status_code == 422


def test_another_customer_is_untouched(fresh):
    staff = fresh.login("staff")
    lehota = fresh.done.customers["Obec Vzorová Lehota"]
    before = _lists(staff, lehota, 2027)
    assert staff.post(f"/api/customers/{fresh.boldog}/years/2027/carry-over").status_code == 200
    assert _lists(staff, lehota, 2027) == before
