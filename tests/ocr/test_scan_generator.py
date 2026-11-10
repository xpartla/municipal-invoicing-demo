"""The scan generator in Chromium (marked `ocr`: it needs Playwright's browser, like the
`ocr` CI job, which generates the full set)."""

import pypdfium2 as pdfium
import pytest

from riso.testdata import printed
from riso.testdata.scans import SAMPLES_DIR, generate, load_truths

pytestmark = pytest.mark.ocr

CASES = ["heldout-07-hornbach-kd", "heldout-35-metro-credit-note", "seed-04-fcc-waste"]


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    first = tmp_path_factory.mktemp("first")
    second = tmp_path_factory.mktemp("second")
    generate(first, only=CASES)
    generate(second, only=CASES)
    return first, second


def test_the_same_seed_gives_byte_identical_files(runs):
    first, second = runs
    names = sorted(p.name for p in first.iterdir())
    assert len(names) == 3 * len(CASES) + 1
    assert names == sorted(p.name for p in second.iterdir())
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_the_truth_matches_the_committed_samples(runs):
    """The truth does not depend on Chromium's pixels, so it equals the committed one on any
    machine; the images may differ slightly with another Chromium build."""
    committed = {t.case_id: t for t in load_truths(SAMPLES_DIR)}
    for truth in load_truths(runs[0]):
        assert truth == committed[truth.case_id]


def test_the_digital_pdf_has_a_text_layer_with_the_fields(runs):
    for truth in load_truths(runs[0]):
        pdf = pdfium.PdfDocument(runs[0] / truth.files["digital_pdf"])
        assert len(pdf) == 1
        text = pdf[0].get_textpage().get_text_range().replace(" ", " ")
        doc = truth.document
        assert doc.invoice.number in text
        assert printed.amount(doc.totals.gross).replace(" ", " ") in text
        assert doc.supplier.ico in text.replace(" ", "")
        if doc.invoice.variable_symbol:
            assert doc.invoice.variable_symbol in text
