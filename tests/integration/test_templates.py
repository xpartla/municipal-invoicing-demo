"""Mapping templates on the database (P2-M3-T04): scopes and visibility across providers,
permissions, saving a run's mapping, and the template chosen for a file by its headers."""

import csv
import io

import pytest

from riso.api.composition import build_services
from riso.audit.domain.event import AuditFilter
from riso.exchange.application.imports import (
    UploadImport,
    create_import,
    preview_import,
    set_mapping,
)
from riso.exchange.application.templates import (
    SaveTemplate,
    TemplateChooser,
    delete_template,
    get_template,
    owned_templates,
    save_run_as_template,
    save_template,
    usable_templates,
)
from riso.exchange.domain.mapping import ColumnMapping, FieldSource, ImportType
from riso.exchange.domain.table import ReadOptions
from riso.exchange.domain.templates import BUILTIN, TOPSET_CHART_HEADER, TemplateScope
from riso.identity.application.access import Grant
from riso.identity.domain import Email, MembershipScope, Role, User
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.platform import Settings
from riso.shared import NotFound, PermissionDenied, RequestContext
from riso.tenancy.domain import ServiceProvider

PASSWORD = "Ukážkové-heslo-2026"
MAPPING = ColumnMapping(
    import_type=ImportType.ACCOUNTS,
    fields={
        "su": FieldSource(column="SU"),
        "au": FieldSource(column="AU"),
        "type": FieldSource(column="Typ účtu"),
    },
)


def _ctx(services, user_id):
    with services.uow(immediate=False) as uow:
        user = uow.users.get(user_id)
        grants = tuple(Grant(m.scope.kind, m.scope.id, m.role) for m in user.active_memberships())
    return RequestContext("test", user_id, policy=services.policy(grants))


@pytest.fixture
def env(tmp_path, seeded_copy):
    """The seed, plus a second provider with the unassigned customer and a staff member."""
    settings = Settings(var_dir=tmp_path / "var", env="test")
    done = seeded_copy(settings.var_dir)
    services = build_services(settings, hasher=Argon2Hasher.fast())
    with services.uow() as uow:
        now = services.clock.now()
        other = ServiceProvider.create(services.ids.new(), "Iná účtovná firma", now)
        uow.providers.add(other)
        alone = uow.customers.get(done.customers["Obec Nezávislá"])
        alone.assign_to(other)
        uow.customers.save(alone)
        staff = User.invite(
            services.ids.new(), "Druhý Účtovník", Email.parse("druhy@ina.test"), now
        )
        staff.set_password(services.hasher.hash(PASSWORD), now)
        staff.grant(
            services.ids.new(), MembershipScope.provider(other.id), Role.PROVIDER_STAFF, now
        )
        uow.users.add(staff)
        uow.commit()
    ctx = {key: _ctx(services, done.users[key][0]) for key in done.users}
    ctx["other_staff"] = _ctx(services, staff.id)
    yield services, done, other.id, ctx
    services.close()


def _save(services, ctx, scope, owner, name="Moja šablóna", signature="sig"):
    return save_template(ctx, services.uow(), SaveTemplate(scope, owner, name, signature, MAPPING))


def test_a_providers_templates_are_invisible_to_another_provider(env):
    services, done, other_id, ctx = env
    boldog, alone = done.customers["Obec Boldog"], done.customers["Obec Nezávislá"]
    mine = _save(services, ctx["staff"], TemplateScope.PROVIDER, done.provider_id, "Vzor – rozvrh")
    theirs = _save(services, ctx["other_staff"], TemplateScope.PROVIDER, other_id, "Iná – rozvrh")

    def ids(user, customer):
        return {
            t.id
            for t in usable_templates(ctx[user], services.uow(), services.customers(), customer)
        }

    assert mine.id in ids("staff", boldog) and theirs.id not in ids("staff", boldog)
    assert theirs.id in ids("other_staff", alone) and mine.id not in ids("other_staff", alone)
    assert mine.id in ids("user", boldog)  # the provider's customers use its templates
    with pytest.raises(NotFound):
        get_template(ctx["other_staff"], services.uow(), services.customers(), alone, mine.id)
    assert [
        t.id
        for t in owned_templates(
            ctx["staff"], services.uow(), TemplateScope.PROVIDER, done.provider_id
        )
    ] == [mine.id]
    with pytest.raises(PermissionDenied):
        owned_templates(ctx["staff"], services.uow(), TemplateScope.PROVIDER, other_id)
    with pytest.raises(PermissionDenied):
        _save(services, ctx["staff"], TemplateScope.PROVIDER, other_id)
    with pytest.raises(PermissionDenied):
        usable_templates(ctx["other_staff"], services.uow(), services.customers(), boldog)


def test_who_makes_which_templates(env):
    services, done, _, ctx = env
    boldog = done.customers["Obec Boldog"]
    _save(services, ctx["user"], TemplateScope.CUSTOMER, boldog)
    _save(services, ctx["admin"], TemplateScope.CUSTOMER, boldog)
    _save(services, ctx["admin"], TemplateScope.GLOBAL, None)
    for user, scope, owner in [
        ("viewer", TemplateScope.CUSTOMER, boldog),
        ("staff", TemplateScope.CUSTOMER, boldog),  # staff make the provider's (plan §5.2)
        ("user", TemplateScope.PROVIDER, done.provider_id),
        ("user", TemplateScope.GLOBAL, None),
        ("staff", TemplateScope.GLOBAL, None),
    ]:
        with pytest.raises(PermissionDenied):
            _save(services, ctx[user], scope, owner)
    with pytest.raises(PermissionDenied):  # a viewer does not import (plan §5.2)
        usable_templates(ctx["viewer"], services.uow(), services.customers(), boldog)
    listed = usable_templates(ctx["user"], services.uow(), services.customers(), boldog)
    scopes = [t.scope for t in listed]
    assert scopes[:2] == [TemplateScope.CUSTOMER, TemplateScope.CUSTOMER]
    assert TemplateScope.GLOBAL in scopes and TemplateScope.BUILTIN in scopes
    accounts = usable_templates(
        ctx["user"], services.uow(), services.customers(), boldog, ImportType.ACCOUNTS
    )
    assert {t.import_type for t in accounts} == {ImportType.ACCOUNTS}
    global_only = usable_templates(ctx["admin"], services.uow(), services.customers(), None)
    assert {t.id for t in global_only if t.builtin} == {
        t.id for t in BUILTIN.values() if t.import_type.is_global
    }


def test_updating_and_deleting(env):
    services, done, _, ctx = env
    boldog = done.customers["Obec Boldog"]
    template = _save(services, ctx["user"], TemplateScope.CUSTOMER, boldog)
    again = save_template(
        ctx["user"],
        services.uow(),
        SaveTemplate(TemplateScope.CUSTOMER, boldog, "Premenovaná", "sig2", MAPPING, template.id),
    )
    assert again.id == template.id and again.name == "Premenovaná"
    with pytest.raises(PermissionDenied):
        delete_template(ctx["viewer"], services.uow(), TemplateScope.CUSTOMER, boldog, template.id)
    with pytest.raises(NotFound):  # a built-in template is not stored, so not deleted
        delete_template(
            ctx["admin"], services.uow(), TemplateScope.GLOBAL, None, "builtin:global-ek"
        )
    delete_template(ctx["user"], services.uow(), TemplateScope.CUSTOMER, boldog, template.id)
    assert owned_templates(ctx["user"], services.uow(), TemplateScope.CUSTOMER, boldog) == []
    with services.uow(immediate=False) as uow:
        events, _ = uow.audit_log.page(AuditFilter(customer_id=boldog, action="templates."))
    assert [e.action for e in events] == [
        "templates.deleted",
        "templates.updated",
        "templates.created",
    ]


def _chart_csv(header) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\n")
    writer.writerow(header)
    writer.writerow(["518", "1", "Nákladový", "", "", "", "Telefóny"])
    return out.getvalue().encode()


def _preview(services, ctx, customer_id, run_id):
    return preview_import(
        ctx,
        services.uow(),
        services.storage,
        services.reader,
        customer_id,
        run_id,
        templates=TemplateChooser(services.uow(immediate=False), services.customers(), customer_id),
    )


def test_the_template_is_chosen_by_the_files_headers(env):
    services, done, _, ctx = env
    boldog, user = done.customers["Obec Boldog"], ctx["user"]

    def upload(header):
        return create_import(
            user,
            services.uow(),
            services.storage,
            services.reader,
            UploadImport(boldog, ImportType.ACCOUNTS, 2026, "rozvrh.csv", _chart_csv(header)),
        )

    run = upload(TOPSET_CHART_HEADER)
    preview = _preview(services, user, boldog, run.id)
    assert preview.template_id == "builtin:topset-chart"
    assert preview.template_name == "TOPSET – Účtový rozvrh"
    assert preview.suggestion == BUILTIN["builtin:topset-chart"].mapping

    # The same headers in another order and case: the same signature, the same template.
    shuffled = upload([h.upper() for h in reversed(TOPSET_CHART_HEADER)])
    other = _preview(services, user, boldog, shuffled.id)
    assert other.signature == preview.signature and other.template_id == "builtin:topset-chart"
    assert other.suggestion.fields["su"].column == "SU"

    # The customer's own template for these headers wins over the built-in one.
    set_mapping(
        user,
        services.uow(),
        services.storage,
        services.reader,
        boldog,
        run.id,
        ReadOptions(header_row=1, delimiter=";"),
        MAPPING,
    )
    saved = save_run_as_template(
        user,
        services.uow(),
        services.storage,
        services.reader,
        boldog,
        run.id,
        scope=TemplateScope.CUSTOMER,
        owner_id=boldog,
        name="Boldog – rozvrh",
    )
    assert saved.signature == preview.signature and saved.mapping == MAPPING
    third = _preview(services, user, boldog, upload(TOPSET_CHART_HEADER).id)
    assert third.template_id == saved.id and third.template_name == "Boldog – rozvrh"

    # Headers no template knows: the suggestion from the headers.
    unknown = upload(["Syntetický účet", "Analytický účet", "Druh", "Názov"])
    fresh = _preview(services, user, boldog, unknown.id)
    assert fresh.template_id is None and fresh.suggestion.fields["su"].column == "Syntetický účet"
