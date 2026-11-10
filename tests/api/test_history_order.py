"""An invoice's history is in the order it was written, even when the clock steps back
between two changes (P2-M5-T14): the WSL2 clock is stepped by the host's time sync."""

from datetime import timedelta

from riso.dataset import load_cases
from riso.shared import FixedClock
from tests.api.conftest import Fresh

TELEKOM = next(c for c in load_cases() if c.id == "anchor-telekom")


def test_the_history_keeps_its_order_when_the_clock_steps_back(fresh: Fresh):
    user = fresh.login("user")
    clock = FixedClock(fresh.services.clock.now())
    fresh.services.clock = clock
    fields = TELEKOM.invoice.model_dump(mode="json")
    invoice = user.post(f"/api/customers/{fresh.boldog}/invoices", json=fields).json()
    clock.advance(timedelta(seconds=-90))  # the clock is set back
    discarded = user.post(
        f"/api/customers/{fresh.boldog}/invoices/{invoice['id']}/discard",
        json={"reason": "zle zadaná"},
    )
    assert discarded.status_code == 200, discarded.text

    with fresh.services.uow(immediate=False) as uow:
        history = uow.invoices.history(fresh.boldog, invoice["id"])
    kinds = [e.kind.value for e in history]
    assert kinds == ["created", "checked", "coded", "discarded"]
    assert history[-1].at < history[0].at  # recorded as the clock said
    api = user.get(f"/api/customers/{fresh.boldog}/invoices/{invoice['id']}/history").json()
    assert [e["kind"] for e in api["items"]] == kinds


def _entered(fresh: Fresh, user, number: str) -> dict:
    fields = TELEKOM.invoice.model_dump(mode="json")
    fields["handwritten"]["number"] = number
    response = user.post(f"/api/customers/{fresh.boldog}/invoices", json=fields)
    assert response.status_code == 201, response.text
    return response.json()


def _book(fresh: Fresh, user, invoice: dict) -> dict:
    coding = {
        "document": invoice["proposal"]["document"],
        "posting": invoice["proposal"]["posting"],
        "budget": invoice["proposal"]["budget"],
    }
    response = user.post(
        f"/api/customers/{fresh.boldog}/invoices/{invoice['id']}/book",
        json={"action": "accepted", "coding": coding},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_invoices_of_one_date_of_supply_keep_their_upload_order_when_the_clock_steps_back(
    fresh: Fresh,
):
    """Decision 61: one date of supply and one handwritten number go by upload order (P2-M5-T15)."""
    user = fresh.login("user")
    clock = FixedClock(fresh.services.clock.now())
    fresh.services.clock = clock
    first = _entered(fresh, user, "300")
    clock.advance(timedelta(seconds=-90))  # the clock is set back before the second upload
    second = _entered(fresh, user, "300")
    assert second["uploaded_at"] < first["uploaded_at"]

    assert _book(fresh, user, first)["invoice"]["number"] == "FD/300/26"
    booked = _book(fresh, user, second)
    assert booked["invoice"]["number"] == "FD/301/26"
    assert booked["placement"]["shifts"] == []
