"""Editing a convention changes the next proposal (P2-M2-T09): the API codes with the stored
conventions of the customer, not with the committed file."""

from riso.dataset import load_cases
from riso.knowledge import load_conventions

NEW_SUPPLIER = "11111119"  # passes the IČO check digit; in no supplier memory


def _telekom_as_a_new_supplier() -> str:
    case = next(c for c in load_cases() if c.id == "anchor-telekom")
    invoice = case.invoice.model_copy(
        update={"supplier": case.invoice.supplier.model_copy(update={"ico": NEW_SUPPLIER})}
    )
    return invoice.model_dump_json()


def _md(client, customer_id) -> str:
    response = client.post(
        f"/api/customers/{customer_id}/code",
        content=_telekom_as_a_new_supplier(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text
    return response.json()["posting"][0]["md"]


def test_editing_a_convention_changes_the_next_proposal(seeded, login):
    boldog = seeded[1].customers["Obec Boldog"]
    client = login("user")
    assert _md(client, boldog) == "518 003"  # Boldog's telecom rule, no precedent

    document = load_conventions("00305863", 2026).model_dump(mode="json")
    for rule in document["au_rules"]["debit"]["518"]["rules"]:
        if rule["au"] == "003":
            rule["au"] = "001"
    url = f"/api/customers/{boldog}/conventions"
    saved = client.put(url, params={"year": 2026}, json={"revision": 1, "document": document})
    assert saved.status_code == 200, saved.text
    assert _md(client, boldog) == "518 001"

    restored = load_conventions("00305863", 2026).model_dump(mode="json")
    client.put(url, params={"year": 2026}, json={"revision": 2, "document": restored})
    assert _md(client, boldog) == "518 003"
