"""A digital PDF's text layer (P2-M5-T04, plan §8.2 "Digital PDFs"): its words come from
pypdfium2, exact, with boxes in the 300-dpi page's pixels; a scanned PDF has none."""

import pytest

from riso.intake.infrastructure.pdftext import text_layer
from riso.testdata import printed
from riso.testdata.scans import SAMPLES_DIR, load_truths

TRUTHS = {t.case_id: t for t in load_truths(SAMPLES_DIR)}


@pytest.mark.parametrize("case_id", sorted(TRUTHS))
def test_every_printed_field_is_in_the_text_layer(case_id):
    truth = TRUTHS[case_id]
    layouts = text_layer((SAMPLES_DIR / truth.files["digital_pdf"]).read_bytes())
    assert layouts is not None and len(layouts) == 1
    page = layouts[0]
    assert page.source == "text_layer" and page.dpi == 300
    assert all(w.confidence == 1.0 for w in page.words)
    text = page.text.replace(" ", " ")
    compact = text.replace(" ", "")
    doc = truth.document
    if doc.supplier.ico:
        assert doc.supplier.ico in compact
    if doc.supplier.iban:
        assert doc.supplier.iban.replace(" ", "") in compact
    if doc.invoice.variable_symbol:
        assert doc.invoice.variable_symbol in text
    assert doc.invoice.number in text
    assert printed.amount(doc.totals.gross).replace(" ", " ") in text


def test_words_have_boxes_on_the_page_and_lines_in_order():
    truth = TRUTHS["heldout-07-hornbach-kd"]
    [page] = text_layer((SAMPLES_DIR / truth.files["digital_pdf"]).read_bytes())
    assert abs(page.width - 2480) <= 2 and abs(page.height - 3508) <= 2
    for word in page.words:
        assert 0 <= word.box.x0 < word.box.x1 <= page.width
        assert 0 <= word.box.y0 < word.box.y1 <= page.height
        assert " " not in word.text
    lines = [line.text for line in page.lines()]
    assert any(line.startswith("HORNBACH") for line in lines)
    assert any("35838949" in line for line in lines)


def test_a_scanned_pdf_has_no_usable_text_layer():
    scan = next(t for t in TRUTHS.values() if t.capture.format == "pdf")
    assert text_layer((SAMPLES_DIR / scan.files["scan"]).read_bytes()) is None
    assert text_layer(b"%PDF-1.4 broken") is None
