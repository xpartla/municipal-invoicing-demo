"""`riso ocr-eval` (P2-M5-T08) on the committed samples, read back by `RecordedReader`."""

import datetime as dt
import json

import pytest

from riso.api.ocr_eval import (
    PRINTED,
    EvalCase,
    evaluate,
    format_report,
    synthetic_case,
)
from riso.cli import main
from riso.intake.domain.extract import Context
from riso.intake.infrastructure.recorded import RecordedReader
from riso.testdata.scans import SAMPLES_DIR, load_truths

NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.UTC)
BOLDOG = Context(customer_ico="00305863", customer_name="Obec Boldog")


def _cases() -> list[EvalCase]:
    return [
        synthetic_case(
            t.case_id,
            (SAMPLES_DIR / t.files["scan"]).read_bytes(),
            t.document,
            group=t.layout,
            note_boxes=[
                (n.box.x0, n.box.y0, n.box.x1, n.box.y1)
                for n in (t.handwriting.date, t.handwriting.number)
                if n is not None
            ],
            scan_size=(t.capture.width, t.capture.height),
            scan_dpi=t.capture.dpi,
        )
        for t in load_truths(SAMPLES_DIR)
    ]


@pytest.fixture(scope="module")
def report():
    return evaluate(_cases(), RecordedReader(), eval_set="synthetic", customer=BOLDOG, now=NOW)


def test_the_report_scores_every_printed_field_and_meets_the_targets(report):
    assert report.cases == 10 and report.pages == 10
    assert [f.field for f in report.fields] == list(PRINTED)
    by_field = {f.field: f for f in report.fields}
    assert by_field["supplier.ico"].right == by_field["supplier.ico"].present == 10
    assert by_field["totals.gross"].accuracy == 1.0
    assert {t.metric for t in report.targets} >= {
        "supplier.ico",
        "totals.gross",
        "invoice.issue_date",
        "invoice.variable_symbol",
        "supplier.iban",
        "silent_rate",
        "seconds_per_page",
        "note_held",
    }
    assert report.met, [t for t in report.targets if not t.met]
    assert report.note.measured == 10 and report.note.held >= 9
    assert report.silent <= 0.02 * report.printed_filled


def test_each_case_says_which_fields_were_wrong(report):
    for result in report.results:
        assert set(result.wrong) <= set(PRINTED) and set(result.silent) <= set(result.wrong)
        assert result.pages == 1 and result.seconds >= 0
    assert report.right_after_check == sum(not r.silent for r in report.results)


def test_the_text_report_lists_the_fields_and_targets(report):
    text = format_report(report)
    assert text.startswith("synthetic: 10 cases, 10 pages, recorded")
    assert "supplier.ico" in text and "targets:" in text and "MISSED" not in text
    # A font is easier to read than a hand (plan §8.6); real scans carry no such label.
    assert "(handwriting in a font: optimistic)" in text
    anchors = evaluate(_cases()[:1], RecordedReader(), eval_set="anchor", customer=BOLDOG, now=NOW)
    assert "optimistic" not in format_report(anchors)


def test_excluded_fields_are_not_scored():
    case = _cases()[0]
    excluded = EvalCase(case.id, case.data, case.truth, exclude=frozenset({"supplier.ico"}))
    report = evaluate([excluded], RecordedReader(), eval_set="anchor", customer=BOLDOG, now=NOW)
    assert {f.field: f.present for f in report.fields}["supplier.ico"] == 0
    assert report.note.measured == 0
    assert all(t.metric != "note_held" for t in report.targets)
    dumped = json.loads(report.model_dump_json())
    assert set(dumped["results"][0]) == {
        "id",
        "group",
        "pages",
        "seconds",
        "wrong",
        "silent",
        "note_held",
    }


def test_riso_ocr_eval_needs_its_scans(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RISO_RAW_DIR", str(tmp_path))
    assert main(["ocr-eval", "--scans", str(tmp_path / "none")]) == 1
    assert "run riso testdata scans" in capsys.readouterr().err
    assert main(["ocr-eval", "--set", "anchor"]) == 1
    assert "FA.xlsx" in capsys.readouterr().err
