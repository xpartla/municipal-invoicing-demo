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
