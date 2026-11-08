"""A customer's lists against the global lists of the year (plan §6.3), rule by rule."""

from datetime import UTC, datetime

import pytest

from riso.codelists.domain import (
    AccountEntry,
    BudgetEntry,
    CodeListVersion,
    CofogEntry,
    EkEntry,
    FindingCode,
    FrameworkAccountEntry,
    FundingSourceEntry,
    GlobalLists,
    ListKind,
    SeriesEntry,
    Severity,
    VersionOrigin,
    has_errors,
    validate_list,
    validate_lists,
)

AT = datetime(2026, 11, 8, tzinfo=UTC)


def _version(kind, entries, customer_id="c1", year=2026):
    return CodeListVersion.first(
        f"{kind}-{customer_id}",
        kind,
        customer_id,
        year,
        entries,
        origin=VersionOrigin.SEED,
        at=AT,
        actor=None,
    )


GLOBAL = {
    ListKind.EK: _version(
        ListKind.EK,
        [
            EkEntry("600", "Bežné výdavky"),
            EkEntry("630", "Tovary a služby"),
            EkEntry("632", "Energie, voda a komunikácie"),
            EkEntry("632001", "Energie"),
            EkEntry("632005", "Telekomunikačné služby"),
            EkEntry("611", "Tarifný plat"),
            EkEntry("111003", "Výnos dane z príjmov"),
        ],
        customer_id=None,
    ),
    ListKind.COFOG: _version(
        ListKind.COFOG,
        [
            CofogEntry("01", "Všeobecné verejné služby"),
            CofogEntry("01.1", "Výkonné a zákonodarné orgány"),
            CofogEntry("01.1.1", "Výkonné a zákonodarné orgány"),
            CofogEntry("09.6.0.1", "Školské stravovanie"),
        ],
        customer_id=None,
    ),
    ListKind.FUNDING_SOURCES: _version(
        ListKind.FUNDING_SOURCES,
        [FundingSourceEntry("41", "Zdroje obce"), FundingSourceEntry("72f", "Stravné")],
        customer_id=None,
    ),
    ListKind.FRAMEWORK_ACCOUNTS: _version(
        ListKind.FRAMEWORK_ACCOUNTS,
        [
            FrameworkAccountEntry("5", "Náklady"),
            FrameworkAccountEntry("51", "Služby"),
            FrameworkAccountEntry("518", "Ostatné služby"),
        ],
        customer_id=None,
    ),
}
LISTS = GlobalLists.of(2026, GLOBAL)


def _position(ek="632005", zdroj="41", oddiel="01", trieda="110", active=True):
    return BudgetEntry(
        ek=ek, zdroj=zdroj, analytika="000", oddiel=oddiel, trieda=trieda, active=active
    )


def _codes(findings):
    return [(f.code, f.severity, f.key, f.value) for f in findings]


def test_a_valid_budget_has_no_findings():
    version = _version(ListKind.BUDGET_EXPENSE, [_position(), _position(oddiel="09", trieda="601")])
    assert validate_list(version, LISTS) == []


@pytest.mark.parametrize(
    ("ek", "valid"),
    [
        ("632005", True),
        ("632001", True),
        ("611000", True),  # položka 611 has no podpoložky
        ("632000", False),  # položka 632 has podpoložky; one of them is needed
        ("632009", False),
        ("630000", False),  # a category, not a položka
        ("600000", False),
        ("612000", False),  # not in the list at all
    ],
)
def test_an_unknown_ek_is_an_error(ek, valid):
    version = _version(ListKind.BUDGET_EXPENSE, [_position(ek=ek)])
    expected = (
        [] if valid else [(FindingCode.UNKNOWN_EK, Severity.ERROR, f"{ek} 41 01 110 000", ek)]
    )
    assert _codes(validate_list(version, LISTS)) == expected


def test_an_unknown_zdroj_is_an_error():
    version = _version(ListKind.BUDGET_EXPENSE, [_position(zdroj="72F")])
    assert _codes(validate_list(version, LISTS)) == [
        (FindingCode.UNKNOWN_ZDROJ, Severity.ERROR, "632005 72F 01 110 000", "72F")
    ]


@pytest.mark.parametrize(
    ("oddiel", "trieda", "valid"),
    [
        ("01", "110", True),
        ("01", "100", True),
        ("09", "601", True),
        ("01", "000", False),
        ("04", "510", False),
    ],
)
def test_an_unknown_function_is_an_error(oddiel, trieda, valid):
    version = _version(ListKind.BUDGET_EXPENSE, [_position(oddiel=oddiel, trieda=trieda)])
    findings = validate_list(version, LISTS)
    if valid:
        assert findings == []
    else:
        assert _codes(findings) == [
            (
                FindingCode.UNKNOWN_FUNCTION,
                Severity.ERROR,
                f"632005 41 {oddiel} {trieda} 000",
                f"{oddiel} {trieda}",
            )
        ]


def test_the_income_budget_is_checked_for_ek_and_zdroj():
    version = _version(
        ListKind.BUDGET_INCOME,
        [
            BudgetEntry(ek="111003", zdroj="41", analytika="000"),
            BudgetEntry(ek="312001", zdroj="111", analytika="000"),
        ],
    )
    assert _codes(validate_list(version, LISTS)) == [
        (FindingCode.UNKNOWN_EK, Severity.ERROR, "312001 111 000", "312001"),
        (FindingCode.UNKNOWN_ZDROJ, Severity.ERROR, "312001 111 000", "111"),
    ]


def test_an_account_outside_the_framework_chart_is_a_warning():
    version = _version(
        ListKind.ACCOUNTS, [AccountEntry("518", "003", "cost"), AccountEntry("519", "000", "cost")]
    )
    findings = validate_list(version, LISTS)
    assert _codes(findings) == [
        (FindingCode.UNKNOWN_SYNTHETIC_ACCOUNT, Severity.WARNING, "519 000", "519")
    ]
    assert not has_errors(findings)


def test_only_synthetic_accounts_count_in_the_framework_chart():
    version = _version(ListKind.ACCOUNTS, [AccountEntry("051", "000", "active")])
    lists = GlobalLists.of(2026, GLOBAL)
    assert "51" not in (lists.framework_accounts or ())
    assert len(validate_list(version, lists)) == 1


def test_inactive_rows_are_not_checked():
    version = _version(ListKind.BUDGET_EXPENSE, [_position(ek="612000", active=False)])
    assert validate_list(version, LISTS) == []


def test_a_missing_global_list_is_one_warning_per_field_it_would_check():
    lists = GlobalLists.of(2026, {})
    budget = _version(ListKind.BUDGET_EXPENSE, [_position(ek="999999")])
    accounts = _version(ListKind.ACCOUNTS, [AccountEntry("999", "000", "cost")])
    findings = validate_lists([budget, accounts], lists)
    assert [(f.code, f.severity, f.kind, f.field, f.value) for f in findings] == [
        (FindingCode.GLOBAL_LIST_MISSING, Severity.WARNING, ListKind.BUDGET_EXPENSE, "ek", "ek"),
        (
            FindingCode.GLOBAL_LIST_MISSING,
            Severity.WARNING,
            ListKind.BUDGET_EXPENSE,
            "zdroj",
            "funding_sources",
        ),
        (
            FindingCode.GLOBAL_LIST_MISSING,
            Severity.WARNING,
            ListKind.BUDGET_EXPENSE,
            "function",
            "cofog",
        ),
        (
            FindingCode.GLOBAL_LIST_MISSING,
            Severity.WARNING,
            ListKind.ACCOUNTS,
            "su",
            "framework_accounts",
        ),
    ]
    assert "no active ek list" in findings[0].message


def test_an_income_budget_without_functions_does_not_need_cofog():
    lists = GlobalLists.of(2026, {k: v for k, v in GLOBAL.items() if k is not ListKind.COFOG})
    version = _version(
        ListKind.BUDGET_INCOME, [BudgetEntry(ek="111003", zdroj="41", analytika="000")]
    )
    assert validate_list(version, lists) == []


def test_lists_without_global_counterparts_are_not_checked():
    version = _version(ListKind.DOCUMENT_SERIES, [SeriesEntry("FD", "1", "FD/XXX/RR", "Faktúry")])
    assert validate_list(version, LISTS) == []


def test_lists_of_another_year_or_a_global_list_are_refused():
    with pytest.raises(ValueError):
        validate_list(_version(ListKind.ACCOUNTS, [], year=2027), LISTS)
    with pytest.raises(ValueError):
        validate_list(GLOBAL[ListKind.EK], LISTS)
    with pytest.raises(ValueError):
        GlobalLists.of(2027, GLOBAL)


def test_a_finding_explains_itself_with_codes_only():
    version = _version(ListKind.BUDGET_EXPENSE, [_position(ek="612000")])
    assert validate_list(version, LISTS)[0].message == (
        "budget_expense 612000 41 01 110 000: ek 612000 is not in the global list"
    )
