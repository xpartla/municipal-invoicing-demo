"""The M0 exit criterion: the four precedents and everything else committed resolve against
the dictionaries, and the checks catch what does not."""

import datetime as dt
from decimal import Decimal

import pytest

from riso.checks import case_errors, run_checks
from riso.contracts import BudgetLine, Coding, DocumentRef, PostingLine
from riso.dataset import load_cases
from riso.engine.s6_validate import check_coding

# Anchor case to (budget key, MD, DAL), as read off Boldog's screenshots.
PRECEDENTS = {
    "anchor-accounting": ("637005 41 01 110 000", "518 001", "321 000"),
    "anchor-telekom": ("632005 41 01 110 000", "518 003", "321 000"),
    "anchor-dpo": ("637004 41 01 110 006", "518 001", "321 000"),
    "anchor-dog-shelter": ("637005 41 03 100 001", "518 001", "321 000"),
}


def test_all_committed_data_passes_the_checks():
    failures = {r.name: r.errors for r in run_checks() if r.errors}

    assert failures == {}


def test_the_anchor_cases_are_the_four_precedents():
    anchors = {c.id: c for c in load_cases() if c.split == "anchor"}

    assert set(anchors) == set(PRECEDENTS)
    for case_id, (key, md, dal) in PRECEDENTS.items():
        coding = anchors[case_id].expected.coding
        assert [
            (b.key, p.md, p.dal) for b, p in zip(coding.budget, coding.posting, strict=True)
        ] == [(key, md, dal)]
        assert anchors[case_id].invoice.customer.ico == "00305863"


def _coding(key="632005 41 01 110 000", md="518 003", dal="321 000", amount="93.71", **document):
    ek, zdroj, oddiel, trieda, analytika = key.split(" ")
    return Coding(
        document=DocumentRef(
            **{"series": "FD", "number": "FD/144/26", "booking_date": dt.date(2026, 6, 23)}
            | document
        ),
        posting=[PostingLine(md=md, dal=dal, amount=Decimal(amount), text="x")],
        budget=[
            BudgetLine(
                key=key,
                ek=ek,
                zdroj=zdroj,
                oddiel=oddiel,
                trieda=trieda,
                analytika=analytika,
                amount=Decimal("93.71"),
                text="x",
            )
        ],
    )


def test_a_valid_coding_passes(index):
    validation = check_coding(_coding(), index, gross=Decimal("93.71"))

    assert validation.ok
    assert validation.errors == []


@pytest.mark.parametrize(
    ("coding", "error"),
    [
        (_coding(md="518 999"), "MD 518 999 is not in the chart of accounts"),
        (_coding(key="632005 41 01 110 999"), "is not in the approved budget"),
        (_coding(md="321 000"), "MD 321 000 is not a cost account"),
        (_coding(key="717001 41 01 110 001", md="518 001"), "not an acquisition account 04x"),
        (_coding(dal="379 000"), "DAL 379 000 is not a supplier account"),
        (_coding(amount="93.70"), "posting amount 93.70 differs from budget amount 93.71"),
        (_coding(series="XY"), "series XY is not among the document series"),
        (_coding(number="FD/144/25"), "belongs to another year"),
        (_coding(number="FD/44/26"), "does not follow the pattern FD/XXX/RR"),
    ],
)
def test_broken_invariants_are_reported(index, coding, error):
    validation = check_coding(coding, index, gross=Decimal("93.71"))

    assert not validation.ok
    assert any(error in e for e in validation.errors), validation.errors


def test_a_capital_expense_on_an_acquisition_account_passes(index):
    coding = _coding(key="717001 41 01 110 001", md="042 001")

    assert check_coding(coding, index, gross=Decimal("93.71")).ok


def test_the_sum_must_match_the_invoice_gross(index):
    validation = check_coding(_coding(), index, gross=Decimal("100.00"))

    assert validation.errors == ["budget lines sum to 93.71, the invoice gross is 100.00"]


def test_the_expected_booking_date_and_number_come_from_the_handwriting(source):
    case = next(c for c in load_cases() if c.id == "anchor-telekom")
    document = case.expected.coding.document
    wrong = case.model_copy(deep=True)
    wrong.expected.coding.document = document.model_copy(
        update={"booking_date": dt.date(2026, 6, 22), "number": "FD/145/26"}
    )

    assert case_errors(case, source) == []
    assert case_errors(wrong, source) == [
        "booking date 2026-06-22 is not the handwritten date 2026-06-23",
        "number FD/145/26 is not the handwritten 144",
    ]
