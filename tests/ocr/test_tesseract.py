"""Tesseract on the committed synthetic samples, in its process pool (marked `ocr`)."""

import hashlib
import json

import pytest

from riso.intake.application.ports import PageImage
from riso.intake.domain import MediaType, sniff
from riso.intake.infrastructure.imaging import load_pages
from riso.intake.infrastructure.recorded import RECORDINGS_DIR, RecordedReader
from riso.testdata.scans import SAMPLES_DIR, load_truths

pytestmark = pytest.mark.ocr


def _pages(name: str) -> list[PageImage]:
    data = (SAMPLES_DIR / name).read_bytes()
    media_type = sniff(data)
    assert isinstance(media_type, MediaType)
    sha = hashlib.sha256(data).hexdigest()
    return [
        PageImage(image, index=i, dpi=dpi, document_sha256=sha)
        for i, (image, dpi) in enumerate(load_pages(data, media_type))
    ]


def test_tesseract_reads_a_synthetic_scan(tesseract):
    truth = next(t for t in load_truths(SAMPLES_DIR) if t.case_id == "heldout-07-hornbach-kd")
    [page] = _pages(truth.files["scan"])
    layout = tesseract.read(page)

    text = layout.text
    assert layout.width == page.image.width and layout.dpi == page.dpi
    assert len(layout.words) > 100
    # The page as loaded, before T04's preprocessing: the clear print is read.
    assert "HORNBACH" in text and "Faktúra" in text
    assert truth.document.supplier.ico in text.replace(" ", "")
    assert truth.document.supplier.dic in text
    assert all(0 <= w.confidence <= 1 for w in layout.words)
    assert tesseract.version.startswith("5.5.3 tessdata_best 4.1.0")


def test_the_recorded_layouts_replay_what_tesseract_reads(tesseract):
    """Each committed sample's recording is what Tesseract reads from it now (the same
    models and build; another build may move a few words, so 98% of them must agree)."""
    engine = json.loads((RECORDINGS_DIR / "engine.json").read_text())
    assert engine["version"] == tesseract.version
    recorded = RecordedReader()
    for truth in load_truths(SAMPLES_DIR):
        for page in _pages(truth.files["scan"]):
            replayed, read = recorded.read(page), tesseract.read(page)
            same = sum(a == b for a, b in zip(replayed.words, read.words, strict=False))
            assert same >= 0.98 * max(len(replayed.words), len(read.words)), truth.case_id
