"""`POST /api/customers/{id}/code` (P2-M2-T05): coding from the database. On the seeded
database, the four anchors are coded exactly as `riso code` codes them from the files."""

import pytest

from riso.api import Settings, create_app
from riso.api.adapters import DatabaseReferenceSource
from riso.api.composition import build_services
from riso.api.seed import seed
from riso.contracts import CodingProposal
from riso.dataset import load_cases
from riso.engine import code_invoice
from riso.eval import compare, evaluate
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.knowledge import knowledge_for
from riso.platform import Settings as PlatformSettings
from riso.reference import LocalReferenceSource
from riso.shared import AllowAll, RequestContext
from riso.store import StateStore
from tests.api.conftest import ApiClient

PASSWORD = "Ukážkové-heslo-2026"
BOLDOG = "00305863"
ANCHORS = {c.id: c for c in load_cases() if c.split == "anchor"}


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    settings = PlatformSettings(var_dir=tmp_path_factory.mktemp("coding") / "var", env="test")
    done = seed(settings, password=PASSWORD, hasher=Argon2Hasher.fast())
    services = build_services(settings, hasher=Argon2Hasher.fast())
    app = create_app(
        Settings(var_dir=settings.var_dir, platform=settings, run_worker=False), services=services
    )
    yield app, done, settings.var_dir
    services.close()


def _client(app, done, key="user"):
    client = ApiClient(app)
    client.login(done.users[key][1], PASSWORD)
    return client


def _from_files(case, var_dir) -> CodingProposal:
    """What `riso code` gives, with the same (initial) supplier state as the route."""
    source, state = LocalReferenceSource(), StateStore(var_dir)
    entity = source.context(BOLDOG)
    return code_invoice(
        case.invoice,
        entity=entity,
        bundle=source.bundle(BOLDOG, entity.reference_period),
        memory=state.supplier_memory(BOLDOG),
        counters=state.counters(BOLDOG),
        knowledge=knowledge_for(BOLDOG, entity.budget_year),
    )


@pytest.mark.parametrize("case_id", sorted(ANCHORS))
def test_an_anchor_is_coded_from_the_database_exactly(seeded, case_id):
    app, done, var_dir = seeded
    case = ANCHORS[case_id]
    response = _client(app, done).post(
        f"/api/customers/{done.customers['Obec Boldog']}/code",
        content=case.invoice.model_dump_json(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text
    proposal = CodingProposal.model_validate(response.json())
    assert compare(proposal, case) is None
    assert proposal.model_dump() == _from_files(case, var_dir).model_dump()


def test_the_telekom_anchor_from_the_database(seeded):
    app, done, var_dir = seeded
    telekom = ANCHORS["anchor-telekom"]
    response = _client(app, done, "staff").post(
        f"/api/customers/{done.customers['Obec Boldog']}/code",
        content=telekom.invoice.model_dump_json(),
        headers={"Content-Type": "application/json"},
    )
    body = response.json()
    assert body["bundle_id"] == "00305863/2026-08"
    assert [
        (b["key"], p["md"], p["dal"]) for b, p in zip(body["budget"], body["posting"], strict=True)
    ] == [("632005 41 01 110 000", "518 003", "321 000")]


def test_a_customer_without_lists_gets_409(seeded):
    app, done, var_dir = seeded
    response = _client(app, done, "staff").post(
        f"/api/customers/{done.customers['Obec Vzorová Lehota']}/code",
        content=ANCHORS["anchor-telekom"].invoice.model_dump_json(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 409


def test_a_viewer_may_not_code(seeded):
    app, done, var_dir = seeded
    response = _client(app, done, "viewer").post(
        f"/api/customers/{done.customers['Obec Boldog']}/code",
        content=ANCHORS["anchor-telekom"].invoice.model_dump_json(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 403


@pytest.mark.parametrize("split", ["heldout", "anchor"])
def test_the_evaluation_on_the_database_equals_the_one_on_the_files(seeded, split):
    app, _, _ = seeded
    services = app.state.services
    ctx = RequestContext(request_id="test", actor_id=None, policy=AllowAll())
    source = DatabaseReferenceSource(
        lambda: services.uow(immediate=False), services.reference_data(), ctx
    )
    on_db = evaluate(split, entity=BOLDOG, source=source, knowledge_of=source.knowledge)
    on_files = evaluate(split, entity=BOLDOG)
    assert on_db.model_dump(exclude={"generated_at"}) == on_files.model_dump(
        exclude={"generated_at"}
    )
