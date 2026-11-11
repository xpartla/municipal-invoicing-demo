"""Domov's numbers through `GET /api/customers/{id}/dashboard` (P2-M7-T01, plan §10.2,
decision 67).

A hand-built fixture: dataset invoices of Boldog's uploaded, coded, booked, discarded and
failed at known instants with a frozen clock, several just before or after midnight in
Bratislava; the expected numbers are written out. Then the exit criterion of plan §14: on the
seeded data, the numbers match plain queries of the invoice table."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from riso.api import Settings, create_app
from riso.api.composition import build_services
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.invoicing.application import BookInvoice, book_invoice, discard_invoice
from riso.invoicing.domain.invoice import Actor, Channel, Invoice
from riso.invoicing.infrastructure.orm import InvoiceRow
from riso.platform import Settings as PlatformSettings
from riso.shared import AllowAll, FixedClock, RequestContext
from tests.api.conftest import ApiClient
from tests.conftest import SEED_PASSWORD, copy_seeded
from tests.factories import make_invoice

CTX = RequestContext("test", None, policy=AllowAll())
NOW = datetime(2026, 12, 2, 9, 0, tzinfo=UTC)
"""When the dashboard is read (the onboarding year is 2026)."""


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


class Built:
    def __init__(self, services, clock, app, done) -> None:
        self.services, self.clock, self.app, self.done = services, clock, app, done
        self.boldog = done.customers["Obec Boldog"]
        self.ids: dict[str, str] = {}

    def upload(self, key: str, case_id: str, at: datetime, *, check: bool = True) -> str:
        self.clock.set(at)
        self.ids[key] = make_invoice(self.services, self.boldog, case_id, check=check)
        return self.ids[key]

    def fail(self, key: str, at: datetime) -> None:
        self.clock.set(at)
        actor = Actor.system()
        invoice = Invoice.uploaded(
            self.services.ids.new(), self.boldog, Channel.SCAN, "doc-1", at=at, actor=actor
        )
        invoice.start_extraction("job-1", at, actor)
        invoice.extraction_failed("unreadable", at, actor)
        with self.services.uow() as uow:
            uow.invoices.add(invoice)
            uow.commit()
        self.ids[key] = invoice.id

    def invoice(self, key: str) -> Invoice:
        with self.services.uow(immediate=False) as uow:
            return uow.invoices.get(self.boldog, self.ids[key])

    def book(self, key: str, at: datetime, *, like: str | None = None) -> None:
        """Accepts the proposal; or, for a proposal without lines (a credit note), books
        the first line of `like`'s booking with the invoice's own total."""
        self.clock.set(at)
        invoice = self.invoice(key)
        assert invoice.proposal is not None
        action, coding = "accepted", None
        if like is not None:
            model = self.invoice(like).booking.coding
            gross = invoice.fields.totals.gross
            coding = model.model_copy(
                update={
                    "document": invoice.proposal.document,
                    "posting": [model.posting[0].model_copy(update={"amount": gross})],
                    "budget": [model.budget[0].model_copy(update={"amount": gross})],
                }
            )
            action = "corrected"
        book_invoice(
            CTX,
            self.services.uow(),
            self.services.reference_data(),
            BookInvoice(self.boldog, self.ids[key], action, coding or invoice.proposal.coding()),
        )

    def discard(self, key: str, at: datetime) -> None:
        self.clock.set(at)
        discard_invoice(CTX, self.services.uow(), self.boldog, self.ids[key])

    def client(self, key: str = "viewer") -> ApiClient:
        client = ApiClient(self.app)
        client.login(self.done.users[key][1], SEED_PASSWORD)
        return client


@pytest.fixture(scope="module")
def built(seed_template, tmp_path_factory):
    """Boldog's seeded copy with these invoices (Bratislava times in the comments):

    | key | case | uploaded | then |
    |---|---|---|---|
    | a | anchor-telekom (FD, 93.71) | 1 Nov 00:30 | booked 5 Nov 23:59 |
    | b | heldout-06-telekom-fees (FD, 89.41) | 2 Nov 09:00 | booked 6 Nov 00:00 |
    | c | heldout-18-penam-canteen (FDŠJ, 88.64) | 15 Oct 10:00 | booked 10 Nov 11:00 |
    | d | heldout-35-metro-credit-note (FD, -44.94, review) | 3 Nov 10:00 | corrected 20 Nov 10:00 |
    | e | heldout-01-soza-village-day (review) | 4 Nov 10:00 | stays needs_review |
    | f | seed-02-spp-gas-ocu (ready) | 31 Oct 23:30 | stays ready |
    | g | heldout-14-kaufland-ms-cleaning, unchecked | 30 Nov 23:59 | stays extracted |
    | h | heldout-27-alza-notebook, unchecked | 1 Dec 00:00 | stays extracted |
    | i | a scan whose extraction failed | 12 Nov 10:00 | |
    | j | anchor-dpo (FD, 30.75) | 1 Oct 10:00 | booked 31 Oct 23:59 |
    | l | heldout-15-elektrikar-vo (ready) | 7 Nov 10:00 | discarded 7 Nov 11:00 |
    """
    var_dir = tmp_path_factory.mktemp("dashboard") / "var"
    done = copy_seeded(seed_template, var_dir)
    clock = FixedClock(NOW)
    settings = PlatformSettings(var_dir=var_dir, env="test")
    services = build_services(settings, clock=clock, hasher=Argon2Hasher.fast())
    app = create_app(
        Settings(var_dir=var_dir, platform=settings, run_worker=False), services=services
    )
    b = Built(services, clock, app, done)
    b.upload("a", "anchor-telekom", utc(2026, 10, 31, 23, 30))
    b.upload("b", "heldout-06-telekom-fees", utc(2026, 11, 2, 8))
    b.upload("c", "heldout-18-penam-canteen", utc(2026, 10, 15, 8))
    b.upload("d", "heldout-35-metro-credit-note", utc(2026, 11, 3, 9))
    b.upload("e", "heldout-01-soza-village-day", utc(2026, 11, 4, 9))
    b.upload("f", "seed-02-spp-gas-ocu", utc(2026, 10, 31, 22, 30))
    b.upload("g", "heldout-14-kaufland-ms-cleaning", utc(2026, 11, 30, 22, 59), check=False)
    b.upload("h", "heldout-27-alza-notebook", utc(2026, 11, 30, 23, 0), check=False)
    b.fail("i", utc(2026, 11, 12, 9))
    b.upload("j", "anchor-dpo", utc(2026, 10, 1, 8))
    b.upload("l", "heldout-15-elektrikar-vo", utc(2026, 11, 7, 9))
    b.book("j", utc(2026, 10, 31, 22, 59))
    b.book("a", utc(2026, 11, 5, 22, 59))
    b.book("b", utc(2026, 11, 5, 23, 0))
    b.book("c", utc(2026, 11, 10, 10))
    b.book("d", utc(2026, 11, 20, 9), like="a")
    b.discard("l", utc(2026, 11, 7, 10))
    clock.set(NOW)
    yield b
    services.close()


@pytest.fixture(scope="module")
def november(built):
    response = built.client().get(
        f"/api/customers/{built.boldog}/dashboard", params={"month": "2026-11"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_fixture_is_in_the_states_it_describes(built):
    states = {k: built.invoice(k).state.value for k in built.ids}
    assert states == {
        "a": "booked",
        "b": "booked",
        "c": "booked",
        "d": "booked",
        "e": "needs_review",
        "f": "ready",
        "g": "extracted",
        "h": "extracted",
        "i": "extraction_failed",
        "j": "booked",
        "l": "discarded",
    }
    assert built.invoice("d").needs_review and not built.invoice("a").needs_review


def test_the_tiles(november):
    assert november["month"] == "2026-11"
    assert november["tiles"] == {
        "uploaded": 7,  # a b d e g i l; not c, f, j (October) or h (December)
        "waiting": 1,  # g
        "review": 1,  # e (d was booked)
        "failed": 1,  # i
        "booked": 4,  # a b c d; not j (31 October, 23:59)
        "booked_total": 226.82,  # 93.71 + 89.41 + 88.64 - 44.94
    }


def test_booked_per_day(november):
    days = {d["day"]: (d["count"], d["total"]) for d in november["per_day"] if d["count"]}
    assert days == {
        "2026-11-05": (1, 93.71),
        "2026-11-06": (1, 89.41),
        "2026-11-10": (1, 88.64),
        "2026-11-20": (1, -44.94),
    }
    assert len(november["per_day"]) == 30


def test_by_type(november):
    assert november["by_type"] == [
        {"series": "FD", "credit_note": False, "count": 2, "total": 183.12},
        {"series": "FD", "credit_note": True, "count": 1, "total": -44.94},
        {"series": "FDŠJ", "credit_note": False, "count": 1, "total": 88.64},
    ]


def test_top_suppliers(built, november):
    names = {k: built.invoice(k).proposal.supplier.name for k in "abcd"}
    expected = [
        ("35763469", names["a"], 2, 183.12),
        ("36283576", names["c"], 1, 88.64),
        ("45952671", names["d"], 1, -44.94),
    ]
    by_count = [
        (s["ico"], s["name"], s["count"], s["total"]) for s in november["suppliers_by_count"]
    ]
    assert by_count == expected
    by_amount = [(s["ico"], s["total"]) for s in november["suppliers_by_amount"]]
    assert by_amount == [("35763469", 183.12), ("36283576", 88.64), ("45952671", -44.94)]


def test_units_follow_the_booked_lines(built, november):
    expected: defaultdict[str, list] = defaultdict(lambda: [set(), Decimal(0)])
    for key in "abcd":
        booking = built.invoice(key).booking
        for line in booking.coding.budget:
            function = f"{line.oddiel} {line.trieda}"
            expected[function][0].add(key)
            expected[function][1] += line.amount
    got = {u["function"]: (u["invoices"], u["total"]) for u in november["units"]}
    assert got == {f: (len(keys), float(total)) for f, (keys, total) in expected.items()}
    named = {u["function"]: (u["code"], u["name"]) for u in november["units"]}
    assert named["01 110"] == ("01.1.1", named["01 110"][1]) and named["01 110"][1]


def test_twelve_months(november):
    months = {m["month"]: (m["count"], m["total"]) for m in november["months"]}
    assert list(months) == [
        "2025-12",
        *(f"2026-{m:02d}" for m in range(1, 12)),
    ]
    assert {m: v for m, v in months.items() if v[0]} == {
        "2026-10": (1, 30.75),  # j
        "2026-11": (4, 226.82),
    }


def test_review_rate_and_median_time(built, november):
    waits = sorted(built.invoice(k).booked_at - built.invoice(k).uploaded_at for k in "abcd")
    assert waits[0] == timedelta(days=3, hours=15)  # b
    median = (waits[1] + waits[2]) / 2  # a (4 d 23 h 29 min) and d (17 d)
    assert november["review"] == {
        "booked": 4,
        "reviewed": 1,  # d
        "rate": 0.25,
        "median_seconds": round(median.total_seconds()),
    }
    assert november["review"]["median_seconds"] == (430_140 + 1_468_800) // 2


def test_attention_lists_everything_open_whatever_the_month(built, november):
    attention = november["attention"]
    assert attention["failed_total"] == 1
    assert [i["id"] for i in attention["failed"]] == [built.ids["i"]]
    # The 74 seeded invoices (1 January) are open too, and come first: the oldest.
    assert attention["waiting_total"] == 74 + 4  # e f g h
    assert len(attention["waiting"]) == 5
    assert {i["uploaded_at"] for i in attention["waiting"]} == {"2026-01-01T07:00:00Z"}
    assert attention["warnings"] == []


def test_the_onboarding_checklist(november):
    # The seed gives Boldog its address but no bank account.
    assert november["onboarding"] == {
        "year": 2026,
        "profile": False,
        "codelists": True,
        "health": True,
        "first_booked": True,
        "done": False,
    }


def test_the_bank_account_completes_the_profile_and_the_checklist(built):
    user = built.client("user")
    customer = user.get(f"/api/customers/{built.boldog}").json()
    response = user.patch(
        f"/api/customers/{built.boldog}/contact",
        json={"address": customer["address"], "iban": "SK3112000000198742637541"},
    )
    assert response.status_code == 200, response.text
    body = (
        built.client()
        .get(f"/api/customers/{built.boldog}/dashboard", params={"month": "2026-11"})
        .json()
    )
    assert body["onboarding"]["profile"] is True and body["onboarding"]["done"] is True


def test_there_is_no_drawdown_without_budget_amounts(november):
    assert november["budget"] is None


def test_october_counts_what_november_left_out(built):
    body = (
        built.client()
        .get(f"/api/customers/{built.boldog}/dashboard", params={"month": "2026-10"})
        .json()
    )
    assert body["tiles"] == {
        "uploaded": 3,  # c f j
        "waiting": 0,
        "review": 0,
        "failed": 0,
        "booked": 1,  # j
        "booked_total": 30.75,
    }
    assert [d["day"] for d in body["per_day"] if d["count"]] == ["2026-10-31"]


def test_the_month_defaults_to_the_current_one(built):
    body = built.client().get(f"/api/customers/{built.boldog}/dashboard").json()
    assert body["month"] == "2026-12"
    assert body["tiles"]["uploaded"] == 1  # h, on 1 December at 00:00


@pytest.mark.parametrize("month", ["2026-13", "26-11", "november", "2026-1"])
def test_a_malformed_month_is_a_422(built, month):
    response = built.client().get(
        f"/api/customers/{built.boldog}/dashboard", params={"month": month}
    )
    assert response.status_code == 422


def test_the_booked_tile_links_to_the_bookings_of_the_month(built):
    response = built.client().get(
        f"/api/customers/{built.boldog}/invoices",
        params={"booked_from": "2026-11-01", "booked_to": "2026-11-30"},
    )
    found = {row["id"] for row in response.json()["items"]}
    assert found == {built.ids[k] for k in "abcd"}


def test_the_drawdown_follows_the_budget_amounts(built):
    user = built.client("user")
    booking = built.invoice("a").booking
    key = booking.coding.budget[0].key
    overview = user.get(f"/api/customers/{built.boldog}/codelists", params={"year": 2026}).json()
    version = next(x for x in overview["lists"] if x["kind"] == "budget_expense")["version"]
    built.clock.set(NOW)
    response = user.put(
        f"/api/customers/{built.boldog}/codelists/budget_expense/entries/{key}",
        params={"year": 2026},
        json={"version_id": version["id"], "values": {"approved": 1000, "adjusted": 1500.5}},
    )
    assert response.status_code == 200, response.text
    drawn: defaultdict[str, Decimal] = defaultdict(Decimal)
    for k in "abcdj":  # booked, each with a 2026 booking date
        for line in built.invoice(k).booking.coding.budget:
            drawn[line.key] += line.amount
    body = (
        built.client()
        .get(f"/api/customers/{built.boldog}/dashboard", params={"month": "2026-11"})
        .json()
    )
    assert body["budget"] == {
        "year": 2026,
        "rows": [
            {
                "key": key,
                "description": body["budget"]["rows"][0]["description"],
                "budgeted": 1500.5,
                "drawn": float(drawn[key]),
                "share": float(drawn[key] / Decimal("1500.50")),
            }
        ],
        "budgeted": 1500.5,
        "drawn": float(drawn[key]),
        "elsewhere": float(sum(v for k, v in drawn.items() if k != key)),
    }
    # The drawdown is the budget year's: 2025 has no Boldog budget.
    earlier = built.client().get(
        f"/api/customers/{built.boldog}/dashboard", params={"month": "2025-12"}
    )
    assert earlier.json()["budget"] is None


# --- the exit criterion: the seeded data -----------------------------------------------------


def _count(session, *where) -> int:
    return session.scalar(select(func.count()).select_from(InvoiceRow).where(*where)) or 0


def test_on_the_seeded_data_the_numbers_match_queries_of_the_invoice_table(seeded, login):
    app, done, _ = seeded
    boldog = done.customers["Obec Boldog"]
    body = (
        login("viewer")
        .get(f"/api/customers/{boldog}/dashboard", params={"month": "2026-01"})
        .json()
    )
    services = app.state.services
    with services.uow(immediate=False) as uow:
        s, mine = uow.session, InvoiceRow.customer_id == boldog
        january = (
            InvoiceRow.uploaded_at >= utc(2025, 12, 31, 23),
            InvoiceRow.uploaded_at < utc(2026, 1, 31, 23),
        )
        expected = {
            "uploaded": _count(s, mine, *january),
            "waiting": _count(s, mine, *january, InvoiceRow.state == "extracted"),
            "review": _count(s, mine, *january, InvoiceRow.state == "needs_review"),
            "failed": _count(s, mine, *january, InvoiceRow.state == "extraction_failed"),
            "booked": _count(s, mine, InvoiceRow.state.in_(["booked", "exported", "paid"])),
            "booked_total": 0,
        }
        open_ = _count(
            s,
            mine,
            InvoiceRow.state.in_(
                ["uploaded", "extracting", "extracted", "checked", "needs_review", "ready"]
            ),
        )
    assert body["tiles"] == expected
    assert expected["uploaded"] == 74 and expected["review"] > 0
    assert body["attention"]["waiting_total"] == open_ == 74
    assert body["onboarding"]["first_booked"] is False and body["onboarding"]["done"] is False
    assert (body["onboarding"]["codelists"], body["onboarding"]["health"]) == (True, True)
    assert body["budget"] is None
    assert date.fromisoformat(body["per_day"][0]["day"]) == date(2026, 1, 1)


def test_a_customer_without_lists_is_warned_and_not_onboarded(seeded, login):
    _, done, _ = seeded
    second = done.customers["Obec Vzorová Lehota"]
    body = login("staff").get(f"/api/customers/{second}/dashboard").json()
    onboarding = body["onboarding"]
    assert (onboarding["codelists"], onboarding["health"], onboarding["done"]) == (
        False,
        False,
        False,
    )
    codes = {(w["code"], w["subject"]) for w in body["attention"]["warnings"]}
    assert ("list_missing", "accounts") in codes
    assert ("list_missing", "budget_expense") in codes


def test_a_foreign_customer_is_not_found(seeded, login):
    _, done, _ = seeded
    alone = done.customers["Obec Nezávislá"]
    assert login("viewer").get(f"/api/customers/{alone}/dashboard").status_code == 404


@pytest.mark.parametrize("year", [2026, 2031])
def test_the_dashboards_health_errors_are_the_health_reports_errors(seeded, year):
    """Domov finds the errors without reading the lists' entries; they are the full report's
    (2031 has no global knowledge base and no lists)."""
    from riso.codelists import HealthSeverity, health_errors, knowledge_health
    from riso.shared import AllowAll, RequestContext

    app, done, _ = seeded
    services = app.state.services
    ctx = RequestContext("t", None, policy=AllowAll())
    for name in ("Obec Boldog", "Obec Vzorová Lehota"):
        customer_id = done.customers[name]
        memory = services.supplier_state().memory(customer_id)
        report = knowledge_health(ctx, services.uow(immediate=False), customer_id, year, memory)
        with services.uow(immediate=False) as uow:
            cheap = health_errors(uow, customer_id, year)
        assert cheap == [f for f in report if f.severity is HealthSeverity.ERROR], name
        assert cheap or (name, year) == ("Obec Boldog", 2026)
