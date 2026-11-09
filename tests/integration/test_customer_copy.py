"""Creating a customer as a copy (P2-M3-T06), on a seeded database: the copy job gives the new
customer Boldog's lists as new versions it owns, its parameters, conventions and templates;
supplier memory only when asked; never counters or logins. The job runs twice without
copying twice. Staff copy within their provider, admins anywhere."""

import pytest

from riso.api.composition import build_services
from riso.audit.domain.event import AuditFilter
from riso.codelists.domain import ListKind, VersionOrigin
from riso.exchange.application.copy import COPY_JOB, CopyCustomer, CopyOptions, copy_customer
from riso.exchange.application.templates import SaveTemplate, owned_templates, save_template
from riso.exchange.domain.mapping import ColumnMapping, FieldSource, ImportType
from riso.exchange.domain.templates import TemplateScope
from riso.identity.application.access import Grant
from riso.identity.domain import Email, MembershipScope, Role, User
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.jobs import JobStatus, get_customer_job
from riso.platform import Settings
from riso.shared import Ico, NotFound, PermissionDenied, RequestContext
from riso.tenancy import CreateCustomer, CustomerIdentity
from riso.tenancy.domain import ServiceProvider

PASSWORD = "Ukážkové-heslo-2026"
YEAR = 2026
COPY_ICO = "99900033"


def _ctx(services, user_id):
    with services.uow(immediate=False) as uow:
        user = uow.users.get(user_id)
        grants = tuple(Grant(m.scope.kind, m.scope.id, m.role) for m in user.active_memberships())
    return RequestContext("test", user_id, policy=services.policy(grants))


@pytest.fixture
def env(tmp_path, seeded_copy):
    settings = Settings(var_dir=tmp_path / "var", env="test")
    done = seeded_copy(settings.var_dir)
    services = build_services(settings, hasher=Argon2Hasher.fast())
    with services.uow() as uow:
        now = services.clock.now()
        other = ServiceProvider.create(services.ids.new(), "Iná účtovná firma", now)
        uow.providers.add(other)
        staff = User.invite(services.ids.new(), "Druhý Účtovník", Email.parse("d@ina.test"), now)
        staff.grant(
            services.ids.new(), MembershipScope.provider(other.id), Role.PROVIDER_STAFF, now
        )
        uow.users.add(staff)
        uow.commit()
    ctx = {key: _ctx(services, done.users[key][0]) for key in done.users}
    ctx["other_staff"] = _ctx(services, staff.id)
    yield services, done, other.id, ctx, services.supplier_state()
    services.close()


def _copy(services, ctx, source, provider_id, *, ico=COPY_ICO, **options):
    return copy_customer(
        ctx,
        services.uow(),
        CopyCustomer(
            source,
            CreateCustomer(CustomerIdentity("Obec Kópia", ico), provider_id=provider_id),
            CopyOptions(year=YEAR, **options),
        ),
    )


def _run(services):
    return services.worker().run_pending()


def _job(services, ctx, started):
    return get_customer_job(ctx, services.jobs_uow(), started.customer.id, started.job_id)


def test_a_copy_gets_boldogs_lists_as_its_own_new_versions(env):
    services, done, _, ctx, state = env
    boldog = done.customers["Obec Boldog"]
    save_template(
        ctx["user"],
        services.uow(),
        SaveTemplate(
            TemplateScope.CUSTOMER,
            boldog,
            "Boldog – rozvrh",
            "sig",
            ColumnMapping(
                import_type=ImportType.ACCOUNTS,
                fields={
                    "su": FieldSource(column="SU"),
                    "au": FieldSource(column="AU"),
                    "type": FieldSource(column="Typ"),
                },
            ),
        ),
    )
    started = _copy(services, ctx["staff"], boldog, done.provider_id)
    target = started.customer.id
    assert started.customer.provider_id == done.provider_id
    assert _job(services, ctx["staff"], started).status is JobStatus.QUEUED
    assert _run(services) == 1
    job = _job(services, ctx["staff"], started)
    assert job.status is JobStatus.SUCCEEDED, job.last_error
    assert job.result == {
        "year": YEAR,
        "parameters": True,
        "code_lists": sorted(
            k.value for k in ListKind if not k.is_global and k is not ListKind.COST_CENTRES
        ),
        "conventions": True,
        "templates": 1,
    }

    with services.uow(immediate=False) as uow:
        for kind in ListKind:
            if kind.is_global:
                continue
            source = uow.codelists.active(boldog, kind, YEAR)
            copy = uow.codelists.active(target, kind, YEAR)
            if source is None:
                assert copy is None, kind
                continue
            assert copy.id != source.id and copy.customer_id == target, kind
            assert (copy.number, copy.origin) == (1, VersionOrigin.COPY), kind
            assert copy.entries == source.entries, kind
            assert (copy.period, copy.source, copy.warnings) == (
                source.period,
                source.source,
                source.warnings,
            ), kind
        assert (
            uow.parameters.get(target, YEAR).values() == uow.parameters.get(boldog, YEAR).values()
        )
        assert (
            uow.conventions.get(target, YEAR).document == uow.conventions.get(boldog, YEAR).document
        )
        assert uow.logins.of_customers([target]).get(target, []) == []
        events, _ = uow.audit_log.page(AuditFilter(customer_id=target))
    assert [e.action for e in events] == [
        "customer.copied",
        "customer.copy_requested",
        "customer.created",
    ]
    copied = owned_templates(ctx["admin"], services.uow(), TemplateScope.CUSTOMER, target)
    assert [t.name for t in copied] == ["Boldog – rozvrh"]
    # Memory is off by default; counters and invoices are never copied.
    assert state.memory(target).suppliers == []
    assert state.counters(target).model_dump() == {
        "entity_ico": COPY_ICO,
        "last_used": {},
        "used_numbers": [],
    }


def test_memory_is_copied_only_when_asked(env):
    services, done, _, ctx, state = env
    boldog = done.customers["Obec Boldog"]
    started = _copy(services, ctx["admin"], boldog, None, supplier_memory=True, code_lists=False)
    _run(services)
    job = _job(services, ctx["admin"], started)
    assert job.result["suppliers"] == len(state.memory(boldog).suppliers) == 4
    assert "code_lists" not in job.result
    target = started.customer.id
    memory = state.memory(target)
    assert memory.entity_ico == COPY_ICO
    assert memory.suppliers == state.memory(boldog).suppliers
    assert state.counters(target).last_used == {} and state.counters(target).used_numbers == []
    assert started.customer.provider_id is None
    with services.uow(immediate=False) as uow:
        assert uow.codelists.active_ids(started.customer.id, YEAR) == {}


def test_the_job_run_again_copies_nothing_twice(env):
    services, done, _, ctx, _ = env
    boldog = done.customers["Obec Boldog"]
    started = _copy(services, ctx["staff"], boldog, done.provider_id)
    _run(services)
    with services.uow(immediate=False) as uow:
        before = uow.codelists.active_ids(started.customer.id, YEAR)
    with services.jobs_uow(immediate=False) as uow:
        job = uow.jobs.get(started.job_id)
    with services.uow() as uow:  # the same job again, as a retry would run it
        job_id = uow.queue.enqueue(
            COPY_JOB, job.payload, customer_id=job.customer_id, created_by=job.created_by
        )
        uow.commit()
    assert _run(services) == 1
    with services.jobs_uow(immediate=False) as uow:
        again = uow.jobs.get(job_id)
    assert again.status is JobStatus.SUCCEEDED
    assert again.result == {
        "year": YEAR,
        "parameters": False,
        "code_lists": [],
        "conventions": False,
        "templates": 0,
    }
    with services.uow(immediate=False) as uow:
        assert uow.codelists.active_ids(started.customer.id, YEAR) == before


def test_who_copies_what(env):
    services, done, other_id, ctx, _ = env
    boldog, alone = done.customers["Obec Boldog"], done.customers["Obec Nezávislá"]
    for user, source, provider in [
        ("staff", boldog, other_id),  # into another provider
        ("staff", boldog, None),  # unassigned: admins only
        ("user", boldog, done.provider_id),  # customers' users do not create customers
        ("viewer", boldog, done.provider_id),
    ]:
        with pytest.raises(PermissionDenied):
            _copy(services, ctx[user], source, provider)
    with pytest.raises(NotFound):  # a source outside the provider does not leak
        _copy(services, ctx["other_staff"], boldog, other_id)
    with pytest.raises(NotFound):
        _copy(services, ctx["staff"], alone, done.provider_id)
    with services.uow(immediate=False) as uow:
        assert uow.customers.find_active_by_ico(Ico.parse(COPY_ICO)) is None
    started = _copy(services, ctx["admin"], alone, other_id, ico="99900041")
    assert started.customer.provider_id == other_id
    _run(services)
    assert _job(services, ctx["admin"], started).status is JobStatus.SUCCEEDED
    with pytest.raises(NotFound):  # another customer's job is not found
        get_customer_job(ctx["admin"], services.jobs_uow(), boldog, started.job_id)
