"""The global lists of 2026 (P2-M2-T03, loaded through the import tool since P2-M3-T04): the
four committed files import with their built-in templates, and Boldog's lists validate
against them with exactly the findings explained in the log of 2026-11-08."""

import shutil
from collections import defaultdict

import pytest

from riso import paths
from riso.api.composition import build_services
from riso.api.seed import GLOBAL_FILES, SeedRefused, global_years, seed
from riso.codelists import customer_findings
from riso.codelists.domain import FindingCode, ListKind, Severity, VersionOrigin
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.platform import Settings
from riso.shared import AllowAll, RequestContext

CTX = RequestContext(request_id="test", actor_id=None, policy=AllowAll())
ROWS = {
    ListKind.EK: 691,
    ListKind.COFOG: 216,
    ListKind.FUNDING_SOURCES: 285,
    ListKind.FRAMEWORK_ACCOUNTS: 316,
}


def _seed(tmp_path, global_dir=paths.GLOBAL_DIR):
    settings = Settings(var_dir=tmp_path / "var", env="test")
    seed(
        settings, password="Ukážkové-heslo-2026", hasher=Argon2Hasher.fast(), global_dir=global_dir
    )
    return build_services(settings)


def test_the_four_lists_of_2026_import(tmp_path):
    assert global_years(paths.GLOBAL_DIR) == [2026]
    services = _seed(tmp_path)
    try:
        with services.uow(immediate=False) as uow:
            versions = [uow.codelists.active(None, kind, 2026) for kind in ROWS]
            runs = uow.imports.list(None, offset=0, limit=10)
    finally:
        services.close()
    assert {v.kind: len(v.entries) for v in versions} == ROWS
    for version in versions:
        assert version.customer_id is None and version.number == 1
        assert version.origin is VersionOrigin.IMPORT and version.import_run_id is not None
        assert version.source.name == GLOBAL_FILES[version.kind]
        assert version.source.data_rows == ROWS[version.kind]
    assert sorted(run.template_id for run in runs) == sorted(
        f"builtin:global-{kind.value}" for kind in ROWS
    )
    ek = {e.key for v in versions if v.kind is ListKind.EK for e in v.entries}
    assert {"632006", "632007", "632008", "112004", "641021", "721020"} <= ek  # new in 2026


def _global_dir(tmp_path, ek: str):
    root = tmp_path / "global"
    shutil.copytree(paths.GLOBAL_DIR, root)
    (root / "2026" / "ek.csv").write_text(ek, encoding="utf-8")
    return root


def test_a_bad_row_stops_the_seed_naming_its_file_and_row(tmp_path):
    root = _global_dir(tmp_path, "code,name\n632,Energie\n63x,Zlé\n")
    with pytest.raises(SeedRefused, match=r"ek\.csv row 3"):
        _seed(tmp_path, root)


def test_a_wrong_header_stops_the_seed(tmp_path):
    root = _global_dir(tmp_path, "kod,nazov\n632,Energie\n")
    with pytest.raises(SeedRefused, match="does not fit"):
        _seed(tmp_path, root)


@pytest.fixture(scope="module")
def boldog_findings(tmp_path_factory):
    settings = Settings(var_dir=tmp_path_factory.mktemp("seeded") / "var", env="test")
    done = seed(settings, password="Ukážkové-heslo-2026", hasher=Argon2Hasher.fast())
    services = build_services(settings)
    try:
        with services.uow(immediate=False) as uow:
            assert set(uow.codelists.active_ids(None, 2026)) == set(ROWS)
        yield customer_findings(
            CTX, services.uow(immediate=False), done.customers["Obec Boldog"], 2026
        )
    finally:
        services.close()


def _values(findings, code):
    found = defaultdict(set)
    for f in findings:
        if f.code is code:
            found[f.kind].add(f.value)
    return dict(found)


def test_boldogs_errors_are_the_codes_the_2026_lists_dropped(boldog_findings):
    errors = [f for f in boldog_findings if f.severity is Severity.ERROR]
    assert {f.code for f in errors} == {FindingCode.UNKNOWN_EK, FindingCode.UNKNOWN_ZDROJ}
    assert _values(errors, FindingCode.UNKNOWN_EK) == {
        ListKind.BUDGET_EXPENSE: {"622000", "637023", "642003"},
    }
    assert _values(errors, FindingCode.UNKNOWN_ZDROJ) == {
        ListKind.BUDGET_EXPENSE: {"1151", "1152", "1351", "1352"},
        ListKind.BUDGET_INCOME: {"1351", "1352"},
    }


def test_boldogs_warnings_are_polozky_without_detail_and_the_old_chart(boldog_findings):
    warnings = [f for f in boldog_findings if f.severity is Severity.WARNING]
    assert _values(warnings, FindingCode.EK_NOT_DETAILED) == {
        ListKind.BUDGET_EXPENSE: {"612000", "814000"},
        ListKind.BUDGET_INCOME: {"222000", "233000", "454000"},
    }
    old_chart = _values(warnings, FindingCode.UNKNOWN_SYNTHETIC_ACCOUNT)[ListKind.ACCOUNTS]
    assert len(old_chart) == 34
    assert {"224", "352", "572", "578", "681", "689"} <= old_chart
    assert not {"757", "799"} & old_chart  # off-balance-sheet groups are the entity's
    assert {f.code for f in warnings} == {
        FindingCode.EK_NOT_DETAILED,
        FindingCode.UNKNOWN_SYNTHETIC_ACCOUNT,
    }
    assert not any(f.code is FindingCode.UNKNOWN_FUNCTION for f in boldog_findings)
