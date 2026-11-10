"""The field extractor on the committed samples (P2-M5-T05): the recorded Tesseract layouts
reach plan §8.6's targets (supplier IČO, total and issue date at least 95%, VS and IBAN 85%,
silent wrong at most 2% of the printed fields), and the digital PDFs' text layers give every
field. `riso ocr-eval` (P2-M5-T08) measures the whole synthetic set with Tesseract."""

import hashlib
import json
from collections import Counter

import pytest

from riso.intake.domain.extract import DOUBTFUL, Context, FieldExtractor
from riso.intake.domain.layout import DocumentLayout, PageLayout
from riso.intake.infrastructure.pdftext import text_layer
from riso.intake.infrastructure.recorded import RECORDINGS_DIR, recording_name
from riso.testdata.scans import SAMPLES_DIR, load_truths

BOLDOG = Context(customer_ico="00305863", customer_name="Obec Boldog")
PRINTED = (
    "supplier.ico",
    "supplier.dic",
    "supplier.ic_dph",
    "supplier.iban",
    "customer.ico",
    "invoice.number",
    "invoice.issue_date",
    "invoice.delivery_date",
    "invoice.due_date",
    "invoice.variable_symbol",
    "totals.net",
    "totals.vat",
    "totals.gross",
)
TARGETS = {
    "supplier.ico": 0.95,
    "totals.gross": 0.95,
    "invoice.issue_date": 0.95,
    "invoice.variable_symbol": 0.85,
    "supplier.iban": 0.85,
}
TRUTHS = load_truths(SAMPLES_DIR)


def _value(document, path):
    part, name = path.split(".")
    value = getattr(getattr(document, part), name)
    return value.replace(" ", "") if path == "supplier.iban" and value else value


def _score(results):
    """Per field: (right, cases with a value); and the silent wrongs over printed fields."""
    right, present, silent, filled = Counter(), Counter(), 0, 0
    for truth, extracted in results:
        confidence = extracted.document.ocr_meta.confidence
        for path in PRINTED:
            expected, got = _value(truth.document, path), _value(extracted.document, path)
            if expected is not None:
                present[path] += 1
                right[path] += got == expected
            if got is not None:
                filled += 1
                silent += got != expected and confidence.get(path, 0) >= DOUBTFUL
    return right, present, silent, filled


def _scans():
    for truth in TRUTHS:
        data = (SAMPLES_DIR / truth.files["scan"]).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        page = PageLayout.from_json(
            json.loads((RECORDINGS_DIR / recording_name(sha, 0)).read_text())
        )
        layout = DocumentLayout((page,), "recorded", "1")
        yield truth, FieldExtractor().extract(layout, document_id="x", context=BOLDOG)


def test_the_recorded_samples_reach_the_targets():
    right, present, silent, filled = _score(list(_scans()))
    for path, target in TARGETS.items():
        assert right[path] / present[path] >= target, (path, right[path], present[path])
    assert silent <= 0.02 * filled, f"{silent} silent wrong of {filled} printed fields"


@pytest.mark.parametrize("truth", TRUTHS, ids=lambda t: t.case_id)
def test_a_digital_pdf_gives_every_printed_field(truth):
    pages = text_layer((SAMPLES_DIR / truth.files["digital_pdf"]).read_bytes())
    assert pages is not None
    extracted = FieldExtractor().extract(
        DocumentLayout(tuple(pages), "text_layer", "pdfium"),
        document_id="x",
        context=BOLDOG,
        channel="digital_pdf",
    )
    wrong = {
        path: (_value(extracted.document, path), _value(truth.document, path))
        for path in PRINTED
        if _value(truth.document, path) is not None
        and _value(extracted.document, path) != _value(truth.document, path)
    }
    assert wrong == {}
