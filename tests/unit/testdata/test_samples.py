"""The committed samples (testdata/ocr/samples/) are complete, untouched and of the dataset."""

import hashlib
import io
import json

import pytest
from PIL import Image

from riso.dataset import load_cases
from riso.testdata.scans import SAMPLE_CASES, SAMPLES_DIR, load_truths
from riso.testdata.truth import LAYOUT_NAMES


@pytest.fixture(scope="module")
def truths():
    return {truth.case_id: truth for truth in load_truths(SAMPLES_DIR)}


def test_every_sample_is_there_with_its_files(truths):
    assert sorted(truths) == sorted(SAMPLE_CASES)
    for truth in truths.values():
        for name in truth.files.values():
            assert (SAMPLES_DIR / name).is_file(), name


def test_the_files_match_the_manifest():
    manifest = json.loads((SAMPLES_DIR / "manifest.json").read_text())
    assert manifest["seed"] == 2026
    assert sorted(manifest["cases"]) == sorted(SAMPLE_CASES)
    for files in manifest["cases"].values():
        for name, digest in files.items():
            assert hashlib.sha256((SAMPLES_DIR / name).read_bytes()).hexdigest() == digest, name


def test_each_sample_shows_its_dataset_case_and_nothing_else(truths):
    """The truth is the case's InvoiceDocument as committed: synthetic suppliers and made-up
    persons only (plan §8.6), and samples regenerated when the dataset changes."""
    cases = {case.id: case for case in load_cases()}
    for truth in truths.values():
        assert truth.document == cases[truth.case_id].invoice
        assert truth.document.ocr_meta.synthetic


def test_the_samples_cover_the_layouts_captures_and_note_placements(truths):
    values = list(truths.values())
    assert {t.layout for t in values} == set(LAYOUT_NAMES)
    assert {t.capture.mode for t in values} == {"photo", "scanner"}
    assert {t.capture.format for t in values} == {"jpeg", "png", "pdf"}
    assert {t.handwriting.placement for t in values} == {"split", "stacked", "inline", "margin"}
    assert any(t.document.invoice.document_type == "credit_note" for t in values)
    assert any(t.handwriting.date is None for t in values)


def test_the_note_lies_inside_the_scan(truths):
    for truth in truths.values():
        if truth.capture.format == "pdf":
            continue
        image = Image.open(io.BytesIO((SAMPLES_DIR / truth.files["scan"]).read_bytes()))
        assert image.size == (truth.capture.width, truth.capture.height)
        box = truth.handwriting.box()
        assert box is not None
        assert 0 <= box.x0 < box.x1 <= image.width and 0 <= box.y0 < box.y1 <= image.height
