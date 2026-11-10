"""The reference bundle built from the database (P2-M2-T02): after `riso seed`, Boldog's
bundle for 2026 equals the committed `data/bundles/00305863/2026-08.json` field by field, and
the cache keyed by version IDs gives a new bundle once a list has a new version."""

import pytest

from riso import paths
from riso.api.adapters import bundle_entity
from riso.api.composition import build_services
from riso.codelists import BundleCache, customer_knowledge, reference_bundle
from riso.codelists.application.conventions import KnowledgeCache
from riso.codelists.domain import AccountEntry, ListKind, VersionOrigin
from riso.contracts import ReferenceBundle
from riso.knowledge import knowledge_for, load_knowledge
from riso.platform import Settings
from riso.shared import AllowAll, InvalidState, PermissionDenied, RequestContext
from riso.tenancy.application import get_customer

COMMITTED = ReferenceBundle.model_validate_json(
    (paths.BUNDLES_DIR / "00305863" / "2026-08.json").read_bytes()
)
CTX = RequestContext(request_id="test", actor_id=None, policy=AllowAll())


@pytest.fixture
def seeded(tmp_path, seeded_copy):
    settings = Settings(var_dir=tmp_path / "var", env="test")
    done = seeded_copy(settings.var_dir)
    services = build_services(settings)
    yield services, done.customers
    services.close()


def _bundle(services, customer_id, cache, year=2026):
    entity = bundle_entity(get_customer(CTX, services.uow(immediate=False), customer_id))
    return reference_bundle(
        CTX, services.uow(immediate=False), customer_id, year, entity, cache=cache
    )


def test_boldogs_bundle_from_the_database_equals_the_committed_one(seeded):
    services, customers = seeded
    bundle = _bundle(services, customers["Obec Boldog"], BundleCache())
    assert bundle.model_dump() == COMMITTED.model_dump()
    # Field by field, so a difference says where it is.
    for name in ReferenceBundle.model_fields:
        assert getattr(bundle, name) == getattr(COMMITTED, name), name
    assert bundle.warnings and any(p.aliases for p in bundle.budget_positions_expense)


def test_the_cache_is_keyed_by_the_version_ids(seeded):
    services, customers = seeded
    boldog = customers["Obec Boldog"]
    cache = BundleCache()
    first = _bundle(services, boldog, cache)
    assert _bundle(services, boldog, cache) is first and cache.builds == 1

    with services.uow() as uow:
        accounts = uow.codelists.active(boldog, ListKind.ACCOUNTS, 2026)
        added = AccountEntry("518", "099", "cost", description="nový účet")
        successor = accounts.succeed(
            services.ids.new(),
            accounts.with_added(added),
            origin=VersionOrigin.EDIT,
            at=services.clock.now(),
            actor=None,
        )
        uow.codelists.save(accounts)
        uow.codelists.add(successor)
        uow.commit()

    second = _bundle(services, boldog, cache)
    assert cache.builds == 2 and second is not first
    assert "518 099" in [a.key for a in second.accounts]
    assert second.period == "2026-08"  # the edited version has no period of its own here
    assert len(second.accounts) == len(first.accounts) + 1


def test_a_customer_without_lists_has_no_bundle(seeded):
    services, customers = seeded
    with pytest.raises(InvalidState, match="no accounts, budget_expense, document_series list"):
        _bundle(services, customers["Obec Vzorová Lehota"], BundleCache())
    with pytest.raises(InvalidState):
        _bundle(services, customers["Obec Boldog"], BundleCache(), year=2027)


def test_the_bundle_needs_read_access_to_the_customer(seeded):
    services, customers = seeded
    anonymous = RequestContext.anonymous("test")
    entity = bundle_entity(
        get_customer(CTX, services.uow(immediate=False), customers["Obec Boldog"])
    )
    with pytest.raises(PermissionDenied):
        reference_bundle(
            anonymous, services.uow(immediate=False), customers["Obec Boldog"], 2026, entity
        )


def test_boldogs_stored_conventions_give_the_files_knowledge(seeded):
    services, customers = seeded
    knowledge, revision = customer_knowledge(
        CTX, services.uow(immediate=False), customers["Obec Boldog"], 2026, cache=KnowledgeCache()
    )
    assert revision == 1 and knowledge == knowledge_for("00305863", 2026)
    other, revision = customer_knowledge(
        CTX,
        services.uow(immediate=False),
        customers["Obec Vzorová Lehota"],
        2026,
        cache=KnowledgeCache(),
    )
    assert revision == 0 and other == load_knowledge(2026)
