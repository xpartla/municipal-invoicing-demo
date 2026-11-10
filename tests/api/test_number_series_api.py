"""The number series routes (P2-M4-T02): the year's invoice series with their counters, used
numbers and gaps, and the audited edit of the counter."""

from tests.api.conftest import ApiClient


def _boldog(seeded) -> str:
    return seeded[1].customers["Obec Boldog"]


def test_the_invoice_series_of_the_year(seeded, login):
    client: ApiClient = login("viewer")
    response = client.get(f"/api/customers/{_boldog(seeded)}/number-series?year=2026")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["year"] == 2026
    fd, canteen = body["items"]
    assert (fd["series"], fd["pattern"], fd["last_used"]) == ("FD", "FD/XXX/RR", 222)
    assert (fd["last_used_number"], fd["next_number"]) == ("FD/222/26", "FD/223/26")
    assert fd["used"] and {u["kind"] for u in fd["used"]} == {"external"}
    assert [u["sequence"] for u in fd["used"]] == sorted(u["sequence"] for u in fd["used"])
    assert fd["gaps"][0] < fd["gaps"][-1]
    assert (canteen["series"], canteen["last_used"], canteen["next_number"]) == (
        "FDŠJ",
        0,
        "FDŠJ/001/26",
    )


def test_a_year_without_parameters_has_no_series(seeded, login):
    response = login("viewer").get(f"/api/customers/{_boldog(seeded)}/number-series?year=2031")
    assert response.status_code == 200 and response.json()["items"] == []


def test_the_counter_is_edited_by_the_user_and_not_below_a_used_number(seeded, login):
    url = f"/api/customers/{_boldog(seeded)}/number-series/FDŠJ/2026"
    assert login("viewer").put(url, json={"last_used": 3}).status_code == 403
    user = login("user")
    response = user.put(url, json={"last_used": 3})
    assert response.status_code == 200, response.text
    assert (response.json()["last_used"], response.json()["next_number"]) == (3, "FDŠJ/004/26")
    below = user.put(
        f"/api/customers/{_boldog(seeded)}/number-series/FD/2026", json={"last_used": 1}
    )
    assert below.status_code == 422
    assert below.json()["detail"][0]["type"] == "below_used"
    unknown = user.put(
        f"/api/customers/{_boldog(seeded)}/number-series/XY/2026", json={"last_used": 1}
    )
    assert unknown.status_code == 404
    negative = user.put(url, json={"last_used": -1})
    assert negative.status_code == 422
    audit = login("admin").get(
        f"/api/admin/audit?action=number_series.last_used_set&customer_id={_boldog(seeded)}"
    )
    assert audit.status_code == 200, audit.text
    (event,) = audit.json()["items"]
    assert event["details"] == {"series": "FDŠJ", "year": 2026, "before": 0, "after": 3}
