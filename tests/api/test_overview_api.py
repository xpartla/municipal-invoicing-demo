"""Prehľad klientov and Platforma through the API (P2-M7-T02, plan §10.8, §10.9, decision 67):
a hand-built fixture on a seeded copy with a frozen clock, the expected numbers written out,
and isolation: a provider's staff never see another provider's customers."""

from datetime import UTC, datetime, timedelta

import pytest

from riso.api import Settings, create_app
from riso.api.composition import build_services
from riso.audit.infrastructure.orm import AuditEventRow
from riso.identity.domain import Role
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.intake.infrastructure.orm import DocumentRow, ExtractionRow
from riso.invoicing.application import BookInvoice, book_invoice
from riso.invoicing.domain.invoice import Actor, Channel, Invoice
from riso.jobs.domain import Job, RetryPolicy
from riso.jobs.infrastructure.repository import SqlJobRepository
from riso.platform import Settings as PlatformSettings
from riso.platform.mail import MailOutboxRow
from riso.shared import AllowAll, FixedClock, RequestContext
from tests.api.conftest import ApiClient
from tests.conftest import SEED_PASSWORD, copy_seeded
from tests.factories import PASSWORD, make_customer, make_invoice, make_provider, make_user

CTX = RequestContext("test", None, policy=AllowAll())
NOW = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


class Built:
    def __init__(self, services, clock, app, done) -> None:
        self.services, self.clock, self.app, self.done = services, clock, app, done
        self.boldog = done.customers["Obec Boldog"]
        self.second = done.customers["Obec Vzorová Lehota"]
        self.alone = done.customers["Obec Nezávislá"]
        self.provider = done.provider_id

    def upload(self, customer_id: str, case_id: str, at: datetime, *, check: bool = True) -> str:
        self.clock.set(at)
        return make_invoice(self.services, customer_id, case_id, check=check)

    def fail(self, customer_id: str, at: datetime) -> str:
        actor = Actor.system()
        invoice = Invoice.uploaded(
            self.services.ids.new(), customer_id, Channel.SCAN, "doc-x", at=at, actor=actor
        )
        invoice.start_extraction("job-x", at, actor)
        invoice.extraction_failed("unreadable", at, actor)
        with self.services.uow() as uow:
            uow.invoices.add(invoice)
            uow.commit()
        return invoice.id

    def book(self, customer_id: str, invoice_id: str, at: datetime) -> None:
        self.clock.set(at)
        with self.services.uow(immediate=False) as uow:
            proposal = uow.invoices.get(customer_id, invoice_id).proposal
        book_invoice(
            CTX,
            self.services.uow(),
            self.services.reference_data(),
            BookInvoice(customer_id, invoice_id, "accepted", proposal.coding()),
        )

    def client(self, email: str, password: str = SEED_PASSWORD) -> ApiClient:
        client = ApiClient(self.app)
        client.login(email, password)
        return client

    def seeded(self, key: str) -> ApiClient:
        return self.client(self.done.users[key][1])


@pytest.fixture(scope="module")
def built(seed_template, tmp_path_factory):
    """Boldog (the demo provider's), in November 2026 (Bratislava times):

    - anchor-telekom uploaded on 1 Nov 00:30 and booked on 2 Nov;
    - anchor-dpo uploaded on 31 Oct 23:30 (October) and booked on 30 Nov 23:59;
    - heldout-01 (needs review) uploaded on 3 Nov, heldout-14 unchecked (extracted) on
      4 Nov, a scan whose extraction failed on 5 Nov;
    - an import run left open (the seed's are all applied).

    A second provider with a customer of its own and one invoice; a staff member of it.
    """
    var_dir = tmp_path_factory.mktemp("overview") / "var"
    done = copy_seeded(seed_template, var_dir)
    clock = FixedClock(NOW)
    settings = PlatformSettings(var_dir=var_dir, env="test")
    services = build_services(settings, clock=clock, hasher=Argon2Hasher.fast())
    app = create_app(
        Settings(var_dir=var_dir, platform=settings, run_worker=False), services=services
    )
    b = Built(services, clock, app, done)
    telekom = b.upload(b.boldog, "anchor-telekom", utc(2026, 10, 31, 23, 30))
    dpo = b.upload(b.boldog, "anchor-dpo", utc(2026, 10, 31, 22, 30))
    b.upload(b.boldog, "heldout-01-soza-village-day", utc(2026, 11, 3, 9))
    b.upload(b.boldog, "heldout-14-kaufland-ms-cleaning", utc(2026, 11, 4, 9), check=False)
    b.fail(b.boldog, utc(2026, 11, 5, 9))
    b.book(b.boldog, telekom, utc(2026, 11, 2, 9))
    b.book(b.boldog, dpo, utc(2026, 11, 30, 22, 59))
    clock.set(utc(2026, 11, 6, 9))
    user = b.seeded("user")
    response = user.post(
        f"/api/customers/{b.boldog}/imports",
        files={"file": ("ucty.csv", b"SU;AU;Nazov\n518;001;Sluzby\n", "text/csv")},
        data={"import_type": "accounts", "year": "2026"},
    )
    assert response.status_code in (200, 201), response.text

    b.other_provider = make_provider(services, "Iná účtovná firma, s.r.o.")
    b.other_customer = make_customer(services, "Obec Iná", "99900033", provider_id=b.other_provider)
    b.upload(b.other_customer, "anchor-telekom", utc(2026, 11, 7, 9), check=False)
    make_user(
        services,
        "iny.uctovnik@ina-firma.test",
        name="Iný Účtovník",
        role=Role.PROVIDER_STAFF,
        scope_id=b.other_provider,
    )
    clock.set(NOW)
    yield b
    services.close()


def _overview(client, provider_id, month="2026-11"):
    response = client.get(f"/api/providers/{provider_id}/overview", params={"month": month})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_providers_overview_has_a_row_per_customer_and_the_totals(built):
    body = _overview(built.seeded("staff"), built.provider)
    assert body["month"] == "2026-11"
    rows = {r["name"]: r for r in body["rows"]}
    assert list(rows) == ["Obec Boldog", "Obec Vzorová Lehota"]  # by name; not Nezávislá
    boldog = rows["Obec Boldog"]
    assert {k: boldog[k] for k in ("uploaded", "waiting", "review", "failed", "booked")} == {
        "uploaded": 4,  # telekom, heldout-01, heldout-14, the failed scan (dpo: October)
        "waiting": 1,  # heldout-14
        "review": 1,  # heldout-01
        "failed": 1,
        "booked": 2,  # telekom and dpo (30 Nov 23:59)
    }
    assert boldog["missing_lists"] == [] and boldog["open_imports"] == 1
    assert boldog["last_activity"] == "2026-11-30T22:59:00Z"  # dpo's booking, audited
    lehota = rows["Obec Vzorová Lehota"]
    assert lehota["uploaded"] == lehota["booked"] == lehota["open_imports"] == 0
    assert lehota["missing_lists"] == ["accounts", "budget_expense", "document_series"]
    assert body["totals"] == {
        "customers": 2,
        "uploaded": 4,
        "waiting": 1,
        "review": 1,
        "failed": 1,
        "booked": 2,
        "missing_lists": 1,
        "open_imports": 1,
    }


def test_october_counts_the_invoice_uploaded_before_midnight(built):
    boldog = next(
        r
        for r in _overview(built.seeded("staff"), built.provider, "2026-10")["rows"]
        if r["name"] == "Obec Boldog"
    )
    assert (boldog["uploaded"], boldog["booked"]) == (1, 0)  # dpo, booked in November


def test_a_provider_never_sees_another_providers_customers(built):
    other = built.client("iny.uctovnik@ina-firma.test", PASSWORD)
    body = _overview(other, built.other_provider)
    assert [r["name"] for r in body["rows"]] == ["Obec Iná"]
    assert body["totals"]["uploaded"] == 1
    assert other.get(f"/api/providers/{built.provider}/overview").status_code == 404
    staff = built.seeded("staff")
    assert staff.get(f"/api/providers/{built.other_provider}/overview").status_code == 404


def test_an_admin_sees_any_providers_overview(built):
    admin = built.seeded("admin")
    assert [r["name"] for r in _overview(admin, built.other_provider)["rows"]] == ["Obec Iná"]
    assert len(_overview(admin, built.provider)["rows"]) == 2


def test_customer_logins_have_no_overview(built):
    for key in ("user", "viewer"):
        response = built.seeded(key).get(f"/api/providers/{built.provider}/overview")
        assert response.status_code == 404


def test_the_platform_counts(built):
    services = built.services
    with services.uow() as uow:
        s = uow.session
        # Two pages read by OCR in November, one in October; a text layer is not OCR.
        for n, (pages, source, at) in enumerate(
            [
                (2, "ocr", utc(2026, 11, 3)),
                (None, "ocr", utc(2026, 11, 4)),  # an image: one page
                (5, "text_layer", utc(2026, 11, 4)),
                (1, "ocr", utc(2026, 10, 31, 22, 59)),  # 31 October, 23:59
            ]
        ):
            s.add(
                DocumentRow(
                    id=f"doc-{n}",
                    customer_id=built.boldog,
                    sha256=f"{n:064d}",
                    filename=f"scan-{n}.pdf",
                    media_type="application/pdf",
                    size=1,
                    pages=pages,
                    storage_key=f"k{n}",
                    uploaded_at=at,
                )
            )
            s.add(
                ExtractionRow(
                    id=f"ext-{n}",
                    customer_id=built.boldog,
                    document_id=f"doc-{n}",
                    invoice_id="inv",
                    engine="recorded",
                    engine_version="1",
                    source=source,
                    document={},
                    evidence={},
                    warnings=[],
                    page_keys=[],
                    duration_ms=1,
                    created_at=at,
                )
            )
        before = s.query(MailOutboxRow).filter(MailOutboxRow.sent_at.is_(None)).count()
        for mail_id, sent_at in (("mail-sent", NOW), ("mail-unsent", None)):
            s.add(
                MailOutboxRow(
                    id=mail_id,
                    created_at=NOW,
                    to_address="a@b.test",
                    subject="s",
                    body="b",
                    template="t",
                    sent_at=sent_at,
                )
            )
        job = Job.new("job-failed", "noop", {}, NOW, max_attempts=1)
        job.claim(NOW, "w", timedelta(minutes=1))
        job.fail(NOW, "boom", RetryPolicy())
        SqlJobRepository(s).add(job)
        uow.commit()
        logins = [
            actor
            for (actor,) in s.query(AuditEventRow.actor_id).filter(
                AuditEventRow.action == "auth.login", AuditEventRow.at >= NOW - timedelta(7)
            )
        ]
    admin = built.seeded("admin")
    body = admin.get("/api/admin/overview", params={"month": "2026-11"}).json()
    assert body == {
        "month": "2026-11",
        "providers": 2,
        "customers": 4,  # Boldog, Vzorová Lehota, Nezávislá, Iná
        "users": 5,  # the seed's four and the other provider's staff member
        "invoices": 5,  # Boldog's four of November and Iná's
        "ocr_pages": 3,
        "failed_jobs": 1,
        "logins": len(logins) + 1,  # this admin's login is the latest
        "login_users": len(set(logins) | {built.done.users["admin"][0]}),
        "unsent_mail": before + 1,
    }
    assert body["logins"] >= 2


def test_only_admins_see_the_platform_counts(built):
    for key in ("staff", "user", "viewer"):
        assert built.seeded(key).get("/api/admin/overview").status_code == 403
