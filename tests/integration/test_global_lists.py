"""The global lists of 2026 (P2-M2-T03): the four committed files load, and Boldog's lists
validate against them with exactly the findings explained in the log of 2026-11-08."""

from collections import defaultdict

import pytest

from riso import paths
from riso.api.composition import build_services
from riso.api.seed import seed
from riso.codelists import customer_findings
from riso.codelists.domain import FindingCode, ListKind, Severity
from riso.codelists.infrastructure.global_files import (
    FILES,
    GlobalListError,
    global_versions,
    global_years,
    read_entries,
)
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.platform import Settings
from riso.shared import AllowAll, FixedClock, RequestContext, UuidV7Generator
from tests.integration.test_codelists_repo import T0

CTX = RequestContext(request_id="test", actor_id=None, policy=AllowAll())
ROWS = {
    ListKind.EK: 691,
    ListKind.COFOG: 216,
    ListKind.FUNDING_SOURCES: 285,
    ListKind.FRAMEWORK_ACCOUNTS: 316,
}


def test_the_four_lists_of_2026_load():
    assert global_years(paths.GLOBAL_DIR) == [2026]
    clock = FixedClock(T0)
    versions = global_versions(paths.GLOBAL_DIR, 2026, UuidV7Generator(clock), T0)
    assert {v.kind: len(v.entries) for v in versions} == ROWS
    for version in versions:
        assert version.customer_id is None and version.number == 1
        assert version.source is not None and version.source.data_rows == ROWS[version.kind]
    ek = {e.key for v in versions if v.kind is ListKind.EK for e in v.entries}
    assert {"632006", "632007", "632008", "112004", "641021", "721020"} <= ek  # new in 2026


def test_a_bad_row_names_its_file_and_row(tmp_path):
    path = tmp_path / FILES[ListKind.EK]
    path.write_text("code,name\n632,Energie\n63x,Zlé\n", encoding="utf-8")
    with pytest.raises(GlobalListError, match="ek.csv row 3"):
        read_entries(path, ListKind.EK)
    path.write_text("kod,nazov\n", encoding="utf-8")
    with pytest.raises(GlobalListError, match="header"):
        read_entries(path, ListKind.EK)


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
