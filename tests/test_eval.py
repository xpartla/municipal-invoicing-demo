"""The evaluation of plan section 9: scoring one proposal, the metrics over many, supplier
memory that held-out cases never feed, and the dataset checks that keep the split honest."""

import json
import shutil
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from riso import paths
from riso.api import Settings, create_app
from riso.checks import dataset_errors
from riso.cli import main
from riso.contracts import (
    Alternative,
    BudgetLine,
    CaseResult,
    CodingProposal,
    Counters,
    DatasetCase,
    EvalReport,
    LineCodes,
    PostingLine,
)
from riso.dataset import load_cases
from riso.engine import code_invoice
from riso.eval import evaluate
from riso.eval.metrics import metrics, score_case
from riso.knowledge import load_knowledge
from riso.store import StateStore

BOLDOG = "00305863"
SHELTER = ("637005 41 03 100 001", "518 001", "321 000")


def anchor(case_id: str) -> DatasetCase:
    return next(c for c in load_cases() if c.id == case_id)


@pytest.fixture(scope="module")
def telekom(source, tmp_path_factory) -> tuple[DatasetCase, CodingProposal]:
    """The Telekom anchor and the engine's proposal for it, which matches."""
    case = anchor("anchor-telekom")
    entity = source.context(BOLDOG)
    state = StateStore(var_dir=tmp_path_factory.mktemp("var"))
    proposal = code_invoice(
        case.invoice,
        entity=entity,
        bundle=source.bundle(BOLDOG),
        memory=state.supplier_memory(BOLDOG),
        counters=state.counters(BOLDOG),
        knowledge=load_knowledge(entity.budget_year),
    )
    return case, proposal


def lines(*codes: tuple[str, str, str, str]) -> dict:
    """Posting and budget lines from (key, MD, DAL, amount)."""
    posting, budget = [], []
    for key, md, dal, amount in codes:
        ek, zdroj, oddiel, trieda, analytika = key.split(" ")
        posting.append(PostingLine(md=md, dal=dal, amount=Decimal(amount), text="x"))
        budget.append(
            BudgetLine(
                key=key,
                ek=ek,
                zdroj=zdroj,
                oddiel=oddiel,
                trieda=trieda,
                analytika=analytika,
                amount=Decimal(amount),
                text="x",
            )
        )
    return {"posting": posting, "budget": budget}


def expecting(case: DatasetCase, *codes: tuple[str, str, str, str]) -> DatasetCase:
    coding = case.expected.coding.model_copy(update=lines(*codes))
    return case.model_copy(update={"expected": case.expected.model_copy(update={"coding": coding})})


def test_a_matching_proposal_is_correct_in_every_field(telekom):
    case, proposal = telekom

    result = score_case(case, proposal, known=True)

    assert result.correct and result.full_key and result.top3 and result.split_ok
    assert result.fields == dict.fromkeys(("ek", "zdroj", "cofog", "analytika", "md", "dal"), True)
    assert result.number_ok and result.date_ok and result.validation_ok


def test_a_wrong_analytika_misses_the_key_but_not_the_other_fields(telekom):
    case, proposal = telekom
    wrong = proposal.model_copy(
        update=lines(("632005 41 01 110 001", "518 003", "321 000", "93.71"))
        | {
            "alternatives": [
                Alternative(budget_key="632003 41 01 110 001", score=0.5, why="x"),
                Alternative(budget_key="632005 41 01 110 000", score=0.4, why="x"),
            ]
        }
    )

    result = score_case(case, wrong, known=True)

    assert not result.correct and result.full_key is False
    assert result.fields["ek"] and result.fields["md"] and not result.fields["analytika"]
    assert result.top3  # the expected key is the second alternative


def test_split_lines_compare_by_amount_whatever_their_order(telekom):
    case, proposal = telekom
    ocu = ("632005 41 01 110 000", "518 003", "321 000", "60.00")
    ms = ("632003 41 09 111 000", "518 003", "321 000", "33.71")
    split_case = expecting(case, ocu, ms)

    swapped = score_case(split_case, proposal.model_copy(update=lines(ms, ocu)), known=True)
    single = score_case(split_case, proposal, known=True)

    assert swapped.correct and swapped.split_ok and swapped.top3 is None
    assert not single.correct and single.split_ok is False and not any(single.fields.values())


def test_manual_entry_is_correct_only_without_lines(telekom):
    case, proposal = telekom
    credit_note = case.model_copy(
        update={
            "expected": case.expected.model_copy(update={"outcome": "manual_entry", "coding": None})
        }
    )

    coded = score_case(credit_note, proposal, known=True)
    manual = score_case(credit_note, proposal.model_copy(update=lines()), known=True)

    assert not coded.correct and manual.correct
    assert manual.full_key is None and manual.validation_ok is None


def test_an_unreadable_booking_date_is_not_scored(telekom):
    case, proposal = telekom
    coding = case.expected.coding
    unreadable = expecting(case, ("632005 41 01 110 000", "518 003", "321 000", "93.71"))
    unreadable.expected.coding.document = coding.document.model_copy(update={"booking_date": None})

    result = score_case(unreadable, proposal.model_copy(deep=True), known=True)

    assert result.date_ok is None and result.correct


def _result(correct: bool, review: bool) -> CaseResult:
    code = LineCodes(key="632005 41 01 110 000", md="518 003", dal="321 000")
    return CaseResult(
        case_id="x",
        known_supplier=True,
        expected_outcome="coded",
        expected=[code],
        proposed=[code],
        correct=correct,
        full_key=correct,
        fields=dict.fromkeys(("ek", "zdroj", "cofog", "analytika", "md", "dal"), correct),
        needs_review=review,
        confidence=0.5,
    )


def test_review_precision_recall_and_silent_errors():
    results = [
        _result(True, False),
        _result(True, True),
        _result(False, True),
        _result(False, False),
    ]

    found = metrics(results)

    assert (found["review_rate"].hits, found["review_rate"].n) == (2, 4)
    assert (found["review_precision"].hits, found["review_precision"].n) == (1, 2)
    assert (found["review_recall"].hits, found["review_recall"].n) == (1, 2)
    assert (found["silent_errors"].hits, found["silent_errors"].n) == (1, 4)
    assert found["manual_entry"].value is None  # no case expects manual entry


def _variant(
    base: DatasetCase, case_id: str, split: str, *, booked: str, number: str, ico: str, name: str
) -> DatasetCase:
    """A copy of an anchor under another id, split, booking date, number and supplier."""
    data = json.loads(base.model_dump_json())
    data["id"] = data["invoice"]["id"] = case_id
    data["split"] = split
    data["invoice"]["handwritten"] = {"date": booked, "number": number}
    data["invoice"]["supplier"] |= {"ico": ico, "name": name}
    data["invoice"]["ocr_meta"]["synthetic"] = True
    data["invoice"]["invoice"]["variable_symbol"] = case_id
    data["expected"]["coding"]["document"] |= {"number": f"FD/{number}/26", "booking_date": booked}
    return DatasetCase.model_validate(data)


@pytest.fixture
def invoices_dir(tmp_path):
    """The four anchors, one seed case of a new shelter, and three held-out cases: one of that
    shelter and two of another new supplier."""
    directory = tmp_path / "invoices"
    for split in ("anchor", "seed", "heldout"):
        (directory / split).mkdir(parents=True)
    for path in (paths.INVOICES_DIR / "anchor").glob("*.json"):
        shutil.copy(path, directory / "anchor" / path.name)
    base = anchor("anchor-dog-shelter")
    shelter = {"ico": "87654326", "name": "Útulok Vzor"}
    other = {"ico": "11111119", "name": "Vzor, s.r.o."}
    cases = [
        _variant(base, "seed-shelter", "seed", booked="2026-05-04", number="100", **shelter),
        _variant(base, "heldout-shelter", "heldout", booked="2026-09-01", number="230", **shelter),
        _variant(base, "heldout-other-1", "heldout", booked="2026-09-02", number="231", **other),
        _variant(base, "heldout-other-2", "heldout", booked="2026-09-03", number="232", **other),
    ]
    for case in cases:
        path = directory / case.split / f"{case.id}.json"
        path.write_text(case.model_dump_json(indent=2), encoding="utf-8")
    return directory


def test_seed_cases_feed_memory_and_held_out_cases_never_do(invoices_dir):
    report = evaluate("heldout", invoices_dir=invoices_dir)

    known = {r.case_id: r.known_supplier for r in report.cases}
    assert known == {"heldout-shelter": True, "heldout-other-1": False, "heldout-other-2": False}
    assert report.memory == "frozen" and report.precedent_cases == 5
    shelter = next(r for r in report.cases if r.case_id == "heldout-shelter")
    assert shelter.correct and shelter.expected == [
        LineCodes(key=SHELTER[0], md=SHELTER[1], dal=SHELTER[2])
    ]


def test_seed_cases_are_coded_online_with_the_cases_booked_before_them(invoices_dir):
    report = evaluate("seed", invoices_dir=invoices_dir)

    assert report.memory == "online"
    assert [(r.case_id, r.known_supplier) for r in report.cases] == [("seed-shelter", False)]


def test_the_report_names_the_ground_truth_it_measured(invoices_dir):
    first = evaluate("heldout", invoices_dir=invoices_dir)
    (invoices_dir / "heldout" / "heldout-other-2.json").unlink()
    second = evaluate("heldout", invoices_dir=invoices_dir)

    assert len(first.dataset_sha256) == 64
    assert first.dataset_sha256 != second.dataset_sha256


def test_the_committed_held_out_set_validates_in_full():
    report = evaluate("heldout")

    assert report.cases, "no held-out cases"
    assert report.metrics["validation"].value == 1.0, [
        r.case_id for r in report.cases if r.validation_ok is False
    ]
    assert {t.metric for t in report.targets} == {"ek", "full_key", "validation"}


def test_riso_eval_prints_and_stores_the_report(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("RISO_VAR_DIR", str(tmp_path))

    assert main(["eval", "--split", "anchor"]) == 0

    out = capsys.readouterr().out
    assert out.startswith("anchor: 4 cases of 00305863")
    stored = EvalReport.model_validate_json((tmp_path / BOLDOG / "eval-anchor.json").read_bytes())
    assert stored.metrics["correct"].value == 1.0


def test_the_api_serves_the_stored_report_and_refreshes_it(tmp_path):
    client = TestClient(create_app(Settings(var_dir=tmp_path / "var")))

    first = client.get("/api/eval", params={"split": "anchor"})
    again = client.get("/api/eval", params={"split": "anchor"})
    unknown = client.get("/api/eval", params={"entity": "11111119"})

    assert first.status_code == 200 and first.json()["split"] == "anchor"
    assert again.json()["generated_at"] == first.json()["generated_at"]
    assert unknown.status_code == 404


def _counters() -> dict[str, Counters]:
    return {
        BOLDOG: Counters(entity_ico=BOLDOG, last_used={"FD/2026": 222}, used_numbers=["FD/213/26"])
    }


def test_the_dataset_checks_catch_a_dishonest_split():
    base = anchor("anchor-dog-shelter")
    shelter = {"ico": "87654326", "name": "Útulok Vzor"}
    late_seed = _variant(base, "seed-late", "seed", booked="2026-09-10", number="240", **shelter)
    early = _variant(base, "heldout-early", "heldout", booked="2026-09-01", number="240", **shelter)
    used = _variant(base, "heldout-used", "heldout", booked="2026-09-02", number="213", **shelter)
    bad_ico = _variant(base, "heldout-ico", "heldout", booked="2026-09-03", number="241",
                       ico="87654327", name="Útulok Vzor")  # fmt: skip
    real = anchor("anchor-dpo").model_copy(deep=True)

    errors = dataset_errors([late_seed, early, used, bad_ico, real], _counters())

    assert errors == [
        "heldout-early: number FD/240/26 is also taken by seed-late",
        "heldout-used: number FD/213/26 is already used in the initial state",
        "heldout-ico: supplier IČO '87654327' is not valid",
        "seed cases run until 2026-09-10, held-out cases start on 2026-09-01; "
        "the held-out set must come later",
    ]


def test_ocr_noise_cases_may_carry_a_misread_ico():
    base = anchor("anchor-dog-shelter")
    noisy = _variant(base, "heldout-noisy", "heldout", booked="2026-09-03", number="241",
                     ico="52823832", name="OZ Pomoc psíkom")  # fmt: skip
    noisy = noisy.model_copy(update={"tags": ["services", "ocr-noise"]})

    assert dataset_errors([noisy], _counters()) == []
