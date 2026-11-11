"""Locating the handwritten note (P2-M5-T06): the crop holds the note on at least 90% of the
samples; `riso ocr-eval` measures the whole synthetic set."""

import hashlib
import math

import pytest
from PIL import Image, ImageDraw

from riso.intake.application.note import note_readings
from riso.intake.domain import sniff
from riso.intake.domain.extract import Context, FieldExtractor
from riso.intake.domain.layout import Box, DocumentLayout, PageLayout, Word
from riso.intake.infrastructure.handwriting import InkLocator, locate
from riso.intake.infrastructure.imaging import prepare_pages
from riso.intake.infrastructure.recorded import RecordedReader
from riso.testdata.scans import SAMPLES_DIR, load_truths


def to_page(box, page, truth):
    """A truth box (the scan's pixels) on the normalised page: a PDF scan rendered at 300 dpi,
    enlarged, then turned about its centre with the page grown to fit."""
    render = 300 / truth.capture.dpi if truth.capture.format == "pdf" else 1.0
    scale = page.scale * render
    angle = math.radians(page.angle)
    width, height = truth.capture.width * scale, truth.capture.height * scale
    cx, cy = page.image.width / 2, page.image.height / 2
    points = []
    for x, y in ((box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1)):
        dx, dy = x * scale - width / 2, y * scale - height / 2
        points.append(
            (
                cx + dx * math.cos(angle) + dy * math.sin(angle),
                cy - dx * math.sin(angle) + dy * math.cos(angle),
            )
        )
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return Box(math.floor(min(xs)), math.floor(min(ys)), math.ceil(max(xs)), math.ceil(max(ys)))


def _covered(item: Box, crop: Box) -> float:
    part = item.intersection(crop)
    return 0.0 if part is None else part.area / item.area


@pytest.fixture(scope="module")
def samples():
    """Each committed sample's truth, normalised page and recorded layout."""
    reader = RecordedReader()
    found = []
    for truth in load_truths(SAMPLES_DIR):
        data = (SAMPLES_DIR / truth.files["scan"]).read_bytes()
        [page] = prepare_pages(data, sniff(data), hashlib.sha256(data).hexdigest())
        found.append((truth, page, reader.read(page)))
    return found


def test_the_crop_holds_the_note_on_at_least_90_percent_of_the_samples(samples):
    held, total, shares = 0, 0, []
    for truth, page, layout in samples:
        items = [n.box for n in (truth.handwriting.date, truth.handwriting.number) if n]
        region = locate(page.image, layout)
        boxes = [to_page(Box(b.x0, b.y0, b.x1, b.y1), page, truth) for b in items]
        total += 1
        held += all(_covered(b, region.box) >= 0.85 for b in boxes)
        shares.append(region.box.area / (page.image.width * page.image.height))
    assert held >= 0.9 * total, f"{held} of {total}"
    assert sum(shares) / len(shares) < 0.1  # a crop, not the page


def _page_with(words: list[tuple[str, Box]], ink: list[Box]) -> tuple[Image.Image, PageLayout]:
    image = Image.new("L", (2480, 3508), 255)
    draw = ImageDraw.Draw(image)
    for _, box in words:
        draw.rectangle(box.to_list(), fill=30)
    for box in ink:
        for x in range(box.x0, box.x1, 14):  # strokes, not a filled block
            draw.line([(x, box.y0), (x + 8, box.y1)], fill=40, width=5)
    layout = PageLayout(
        0, 2480, 3508, 300, tuple(Word(t, b, 0.95, 0, i) for i, (t, b) in enumerate(words))
    )
    return image, layout


def test_printed_words_are_not_the_note_but_ink_beside_them_is():
    print_line = [("Faktúra", Box(300, 400, 520, 440)), ("č.", Box(540, 400, 580, 440))]
    image, layout = _page_with(print_line, [Box(1200, 150, 1450, 240)])
    region = locate(image, layout)
    assert region.found and region.box.contains(Box(1200, 150, 1450, 240))
    assert region.box.intersection(Box(300, 400, 580, 440)) is None


def test_without_ink_the_crop_is_the_top_band():
    image, layout = _page_with([("Faktúra", Box(300, 400, 520, 440))], [])
    region = InkLocator().locate(image, layout)
    assert not region.found and region.box == Box(0, 0, 2480, round(3508 * 0.12))


def test_rules_and_bars_are_not_ink_of_the_note():
    image = Image.new("L", (2480, 3508), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((200, 300, 2300, 360), fill=40)  # a dark bar
    draw.line([(200, 500), (2300, 500)], fill=0, width=4)  # a rule
    region = locate(image, PageLayout(0, 2480, 3508, 300, ()))
    assert not region.found


def test_reading_the_note_never_fills_the_handwritten_fields(samples):
    """The check step's data: the extracted fields keep the handwritten date and number
    empty, whatever the digits pass read; the readings are only suggestions."""
    reader = RecordedReader()
    for _, page, layout in samples:
        note, readings = note_readings(page, layout, InkLocator(), reader)
        extracted = FieldExtractor().extract(
            DocumentLayout((layout,), "recorded", "1"), document_id="x", context=Context("00305863")
        )
        assert extracted.document.handwritten.date is None
        assert extracted.document.handwritten.number is None
        assert "handwritten.date" not in extracted.document.ocr_meta.confidence
        assert note.page == 0 and note.box.area > 0
