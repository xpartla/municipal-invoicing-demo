"""P2-M3's exit criterion through the HTTP API the wizard uses (plan §2 decision 59; needs
`../data`, skipped without it): Jana uploads TOPSET's four exports, takes the mapping each
preview suggests (the built-in template its headers choose), runs the dry run and applies,
confirming the budgets' errors against the 2026 global lists (decision 58). Boldog's bundle
then equals the committed `data/bundles/00305863/2026-08.json` field by field. The
use-case version of this test is tests/integration/test_topset_import.py."""

from riso import paths
from riso.api import Settings, create_app
from riso.api.adapters import bundle_entity
from riso.api.composition import build_services
from riso.api.seed import seed
from riso.codelists import BundleCache, reference_bundle
from riso.contracts import ReferenceBundle
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.ingest import build
from riso.platform import Settings as PlatformSettings
from riso.shared import AllowAll, RequestContext
from riso.tenancy.application import get_customer
from tests.api.conftest import SEED_PASSWORD, ApiClient

FILES = (
    (build.CHART_FILE, "accounts", "builtin:topset-chart"),
    (build.EXPENSE_FILE, "budget_expense", "builtin:topset-expense"),
    (build.INCOME_FILE, "budget_income", "builtin:topset-income"),
    (build.SERIES_FILE, "document_series", "builtin:topset-series"),
)


def test_importing_topsets_exports_through_http_gives_the_committed_bundle(raw_dir, tmp_path):
    committed = ReferenceBundle.model_validate_json(
        (paths.BUNDLES_DIR / "00305863" / "2026-08.json").read_bytes()
    )
    settings = PlatformSettings(var_dir=tmp_path / "var", env="test")
    done = seed(settings, password=SEED_PASSWORD, hasher=Argon2Hasher.fast())
    services = build_services(settings, hasher=Argon2Hasher.fast())
    app = create_app(
        Settings(var_dir=settings.var_dir, platform=settings, run_worker=False), services=services
    )
    boldog = done.customers["Obec Boldog"]
    jana = ApiClient(app)
    jana.login(done.users["user"][1], SEED_PASSWORD)
    try:
        for name, import_type, template_id in FILES:
            uploaded = jana.post(
                f"/api/customers/{boldog}/imports",
                files={"file": (name, (raw_dir / name).read_bytes())},
                data={"import_type": import_type, "year": "2026"},
            )
            assert uploaded.status_code == 201, uploaded.text
            base = f"/api/customers/{boldog}/imports/{uploaded.json()['id']}"
            preview = jana.get(f"{base}/preview").json()
            assert preview["template_id"] == template_id, name
            mapped = jana.put(
                f"{base}/mapping",
                json={
                    "options": {"sheet": preview["sheet"], "header_row": preview["header_row"]},
                    "mapping": preview["suggestion"],
                    "template_id": preview["template_id"],
                },
            )
            assert mapped.status_code == 200, mapped.text
            assert jana.post(f"{base}/dry-run").status_code == 202
            services.worker().run_pending()
            run = jana.get(base).json()
            report = run["report"]
            assert run["can_apply"], (name, report["errors"][:3])
            assert not [e for e in report["errors"] if not e["confirmable"]], name
            diff = report["diff"]
            assert (diff["added"], diff["removed"], diff["changed"]) == (0, 0, 0), name
            confirm = bool(report["errors"])
            assert confirm == import_type.startswith("budget"), name
            applied = jana.post(f"{base}/apply", json={"confirm_errors": confirm})
            assert applied.status_code == 202, applied.text
            services.worker().run_pending()
            assert jana.get(base).json()["state"] == "applied", name

        system = RequestContext("exit", None, policy=AllowAll())
        entity = bundle_entity(get_customer(system, services.uow(immediate=False), boldog))
        bundle = reference_bundle(
            system, services.uow(immediate=False), boldog, 2026, entity, cache=BundleCache()
        )
    finally:
        services.close()
    for field in ReferenceBundle.model_fields:
        assert getattr(bundle, field) == getattr(committed, field), field
    assert bundle == committed
