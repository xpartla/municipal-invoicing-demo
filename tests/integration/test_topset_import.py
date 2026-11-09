"""P2-M3's exit criterion, locally (needs `../data`, skipped without it): importing TOPSET's
four exports through the import tool, each with the built-in template its headers choose,
gives Boldog's lists equal to the committed bundle `data/bundles/00305863/2026-08.json`:
the entries, the source files, the reading warnings and the period. The transfers, which
TOPSET did not export, stay the seeded mock (plan §2 decision 59).

The expense and income budgets carry 7 codes the 2026 global lists dropped (P2-M2-T03);
they are errors against the global lists, imported with the confirmation (decision 58).

This runs the use cases the wizard calls; P2-M3-T07 adds the same check through the HTTP
API."""

from riso import paths
from riso.api.adapters import bundle_entity
from riso.api.composition import build_services
from riso.api.importing import run_import
from riso.api.seed import seed
from riso.codelists import BundleCache, reference_bundle
from riso.codelists.domain import ListKind, VersionOrigin
from riso.contracts import ReferenceBundle
from riso.exchange.domain.mapping import ImportType
from riso.exchange.domain.run import RunState
from riso.identity.application.access import Grant
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.ingest import build
from riso.platform import Settings
from riso.shared import AllowAll, RequestContext
from riso.tenancy.application import get_customer

COMMITTED = ReferenceBundle.model_validate_json(
    (paths.BUNDLES_DIR / "00305863" / "2026-08.json").read_bytes()
)
FILES = (
    (build.CHART_FILE, ImportType.ACCOUNTS, "builtin:topset-chart"),
    (build.EXPENSE_FILE, ImportType.BUDGET_EXPENSE, "builtin:topset-expense"),
    (build.INCOME_FILE, ImportType.BUDGET_INCOME, "builtin:topset-income"),
    (build.SERIES_FILE, ImportType.DOCUMENT_SERIES, "builtin:topset-series"),
)


def test_importing_topsets_exports_gives_the_committed_bundle(raw_dir, tmp_path):
    settings = Settings(var_dir=tmp_path / "var", env="test")
    done = seed(settings, password="Ukážkové-heslo-2026", hasher=Argon2Hasher.fast())
    services = build_services(settings)
    boldog = done.customers["Obec Boldog"]
    with services.uow(immediate=False) as uow:
        user = uow.users.get(done.users["user"][0])
        grants = tuple(Grant(m.scope.kind, m.scope.id, m.role) for m in user.active_memberships())
        seeded = {
            kind: uow.codelists.active(boldog, kind, 2026).id
            for kind in ListKind
            if not kind.is_global and uow.codelists.active(boldog, kind, 2026)
        }
    ctx = RequestContext("exit", user.id, policy=services.policy(grants))
    try:
        for name, import_type, template_id in FILES:
            data = (raw_dir / name).read_bytes()
            confirm = import_type in (ImportType.BUDGET_EXPENSE, ImportType.BUDGET_INCOME)
            run = run_import(
                services, ctx, boldog, import_type, 2026, name, data, confirm_errors=confirm
            )
            assert run.template_id == template_id, name
            assert run.state is RunState.APPLIED, (name, run.report and run.report.errors[:3])
            report = run.report
            assert not report.hard_errors, name
            if confirm:
                assert {e.code for e in report.errors} <= {"unknown_ek", "unknown_zdroj"}
            else:
                assert not report.errors, name
            # The same lists as the seed's: nothing changes but where the rows came from.
            assert (report.diff.added, report.diff.removed, report.diff.changed) == (0, 0, 0)

        with services.uow(immediate=False) as uow:
            for kind in (
                ListKind.ACCOUNTS,
                ListKind.BUDGET_EXPENSE,
                ListKind.BUDGET_INCOME,
                ListKind.DOCUMENT_SERIES,
            ):
                version = uow.codelists.active(boldog, kind, 2026)
                assert version.origin is VersionOrigin.IMPORT and version.number == 2, kind
            assert (
                uow.codelists.active(boldog, ListKind.TRANSFERS, 2026).id
                == seeded[ListKind.TRANSFERS]
            )

        system = RequestContext("exit", None, policy=AllowAll())
        entity = bundle_entity(get_customer(system, services.uow(immediate=False), boldog))
        bundle = reference_bundle(
            system, services.uow(immediate=False), boldog, 2026, entity, cache=BundleCache()
        )
    finally:
        services.close()
    for field in ReferenceBundle.model_fields:  # field by field, so a difference says where
        assert getattr(bundle, field) == getattr(COMMITTED, field), field
    assert bundle == COMMITTED
