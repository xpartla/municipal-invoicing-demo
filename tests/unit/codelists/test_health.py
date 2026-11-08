"""The knowledge health report (plan §6.5): each finding on a crafted customer."""

from datetime import UTC, date, datetime

from riso.codelists.domain import (
    AccountEntry,
    BudgetEntry,
    CodeListVersion,
    ListKind,
    SeriesEntry,
    VersionOrigin,
)
from riso.codelists.domain.health import HealthCode, HealthSeverity, health_report
from riso.contracts import Precedent, PrecedentLine, SupplierMemory, SupplierRecord
from riso.knowledge import Conventions, load_knowledge, merge

AT = datetime(2026, 11, 8, tzinfo=UTC)
ICO = "11111119"


def _version(kind, entries):
    return CodeListVersion.first(
        f"v-{kind}", kind, "c1", 2026, entries, origin=VersionOrigin.SEED, at=AT, actor=None
    )


def _position(ek, oddiel="01", trieda="110", analytika="000", zdroj="41", active=True):
    return BudgetEntry(
        ek=ek, zdroj=zdroj, analytika=analytika, oddiel=oddiel, trieda=trieda, active=active
    )


LISTS = {
    ListKind.ACCOUNTS: _version(
        ListKind.ACCOUNTS,
        [
            AccountEntry("518", "000", "cost"),
            AccountEntry("518", "003", "cost"),
            AccountEntry("321", "000", "passive"),
            AccountEntry("501", "080", "cost", active=False),
        ],
    ),
    ListKind.BUDGET_EXPENSE: _version(
        ListKind.BUDGET_EXPENSE,
        [
            _position("632005"),
            _position("611000"),
            _position("611000", "09", "111"),
            _position("642001"),
        ],
    ),
    ListKind.DOCUMENT_SERIES: _version(
        ListKind.DOCUMENT_SERIES, [SeriesEntry("FD", "1", "FD/XXX/RR", "Faktúry")]
    ),
}
GLOBAL = {ListKind.EK, ListKind.COFOG, ListKind.FUNDING_SOURCES, ListKind.FRAMEWORK_ACCOUNTS}
CONVENTIONS = Conventions.model_validate(
    {
        "au_rules": {
            "debit": {"518": {"default": "000", "rules": [{"au": "003"}, {"au": "010"}]}},
            "credit": {"321": {"default": "000", "rules": [{"au": "001", "zdroj": ["1BA1"]}]}},
        },
        "canteen": {
            "concepts": ["food"],
            "function": "09 601",
            "zdroj": "72f",
            "ek": "633011",
            "analytika": "008",
            "md": "501 080",
        },
    }
)
KNOWLEDGE = merge(load_knowledge(2026), CONVENTIONS)
EMPTY = SupplierMemory(entity_ico=ICO)


def _found(findings, code):
    return [(f.subject, f.where, f.severity, f.count) for f in findings if f.code is code]


def test_conventions_naming_missing_accounts_and_positions():
    findings = health_report(LISTS, GLOBAL, KNOWLEDGE, EMPTY)
    assert _found(findings, HealthCode.CONVENTION_MISSING_ACCOUNT) == [
        ("518 010", "debit 518", HealthSeverity.WARNING, 1),
        ("321 001", "credit 321", HealthSeverity.WARNING, 1),
        ("501 080", "canteen", HealthSeverity.WARNING, 1),  # inactive counts as missing
    ]
    assert _found(findings, HealthCode.CONVENTION_MISSING_POSITION) == [
        ("633011 72f 09 601 008", "canteen", HealthSeverity.WARNING, 1)
    ]


def test_budget_eks_without_a_bridge_rule_with_their_position_count():
    findings = health_report(LISTS, GLOBAL, KNOWLEDGE, EMPTY)
    assert _found(findings, HealthCode.EK_WITHOUT_BRIDGE) == [
        ("611000", None, HealthSeverity.WARNING, 2),
        ("642001", None, HealthSeverity.WARNING, 1),
    ]


def test_missing_lists_for_the_year():
    lists = {k: v for k, v in LISTS.items() if k is not ListKind.DOCUMENT_SERIES}
    findings = health_report(lists, {ListKind.EK}, KNOWLEDGE, EMPTY)
    assert _found(findings, HealthCode.LIST_MISSING) == [
        ("document_series", None, HealthSeverity.ERROR, 1),
        ("budget_income", None, HealthSeverity.INFO, 1),
        ("transfers", None, HealthSeverity.INFO, 1),
        ("cost_centres", None, HealthSeverity.INFO, 1),
    ]
    assert [f.subject for f in findings if f.code is HealthCode.GLOBAL_LIST_MISSING] == [
        "cofog",
        "funding_sources",
        "framework_accounts",
    ]
    assert findings[0].severity is HealthSeverity.ERROR  # errors come first
    assert findings[-1].severity is HealthSeverity.INFO


def test_precedents_outside_the_active_versions():
    memory = SupplierMemory(
        entity_ico=ICO,
        suppliers=[
            SupplierRecord(
                ico="35763469",
                name="Slovak Telekom",
                precedents=[
                    Precedent(
                        document_number="FD/144/26",
                        booking_date=date(2026, 7, 1),
                        lines=[
                            PrecedentLine(
                                budget_key="632005 41 01 110 000",
                                md="518 003",
                                dal="321 000",
                                budget_text="telefon",
                                posting_text="telefon",
                            ),
                            PrecedentLine(
                                budget_key="632005 41 01 110 001",
                                md="518 004",
                                dal="321 000",
                                budget_text="x",
                                posting_text="x",
                            ),
                        ],
                        source="feedback",
                    )
                ],
            )
        ],
    )
    findings = health_report(LISTS, GLOBAL, KNOWLEDGE, memory)
    assert _found(findings, HealthCode.PRECEDENT_OUTSIDE_LISTS) == [
        ("632005 41 01 110 001", "35763469 FD/144/26", HealthSeverity.WARNING, 1),
        ("518 004", "35763469 FD/144/26", HealthSeverity.WARNING, 1),
    ]
    assert {f.kind for f in findings if f.code is HealthCode.PRECEDENT_OUTSIDE_LISTS} == {
        ListKind.BUDGET_EXPENSE,
        ListKind.ACCOUNTS,
    }


def test_a_healthy_customer_has_only_the_known_gaps():
    lists = {
        **LISTS,
        ListKind.BUDGET_EXPENSE: _version(ListKind.BUDGET_EXPENSE, [_position("632005")]),
    }
    findings = health_report(lists, GLOBAL, load_knowledge(2026), EMPTY)
    assert [f.code for f in findings] == [HealthCode.LIST_MISSING] * 3  # the optional lists


def test_a_year_without_knowledge_is_one_error_and_skips_the_knowledge_checks():
    findings = health_report(LISTS, GLOBAL, None, EMPTY)
    assert _found(findings, HealthCode.KNOWLEDGE_MISSING) == [
        ("knowledge", None, HealthSeverity.ERROR, 1)
    ]
    assert not _found(findings, HealthCode.EK_WITHOUT_BRIDGE)
    assert "knowledge_missing: knowledge" in findings[0].message
