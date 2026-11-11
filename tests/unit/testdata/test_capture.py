"""The handwriting and the capture damage, on small pages (no browser)."""

import datetime as dt
import io
import random

import numpy as np
import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageDraw, ImageFilter

from riso.testdata import augment, handwriting
from riso.testdata.scans import dataset_cases
from riso.testdata.truth import Box


def _page(width=1240, height=1754):
    """A white page at 150 dpi with a black block, small enough to be fast."""
    page = Image.new("RGB", (width, height), "white")
    ImageDraw.Draw(page).rectangle((300, 500, 700, 620), fill="black")
    return page


def _decode(data: bytes, fmt: str, dpi: int) -> Image.Image:
    if fmt == "pdf":  # rendered at the scan's resolution (a PDF's unit is 1/72 inch)
        return pdfium.PdfDocument(data)[0].render(scale=dpi / 72).to_pil()
    return Image.open(io.BytesIO(data))


def test_the_same_seed_gives_the_same_bytes_and_another_seed_others():
    block = {"block": Box(x0=300, y0=500, x1=700, y1=620)}
    first = augment.capture(_page(), 11, block)
    again = augment.capture(_page(), 11, block)
    other = augment.capture(_page(), 12, block)

    assert first[0] == again[0] and first[1] == again[1] and first[2] == again[2]
    assert other[0] != first[0]


@pytest.mark.parametrize("seed", range(12))
def test_a_box_of_the_page_is_mapped_onto_its_pixels_in_the_capture(seed):
    block = Box(x0=300, y0=500, x1=700, y1=620)
    data, info, moved = augment.capture(_page(), seed, {"block": block})
    image = _decode(data, info.format, info.dpi).convert("L")
    pixels = np.asarray(image)
    mapped = moved["block"]

    # A PDF's page is in points, so rendering it back may gain a pixel.
    slack = 1 if info.format == "pdf" else 0
    assert abs(image.width - info.width) <= slack and abs(image.height - info.height) <= slack
    assert 90 <= info.dpi <= 150 and abs(info.rotation) <= 3
    inside = pixels[mapped.y0 : mapped.y1, mapped.x0 : mapped.x1]
    # On the page (inside its corners, away from its edge), the block's dark pixels are all in
    # the mapped box; the page around it is light.
    outline = Image.new("L", image.size, 0)
    ImageDraw.Draw(outline).polygon(info.page, fill=255)
    on_page = np.asarray(outline.filter(ImageFilter.MinFilter(9))) > 0
    page_dark = np.argwhere((pixels < 60) & on_page)
    in_box = (
        (page_dark[:, 0] >= mapped.y0 - 1)
        & (page_dark[:, 0] < mapped.y1 + 1)
        & (page_dark[:, 1] >= mapped.x0 - 1)
        & (page_dark[:, 1] < mapped.x1 + 1)
    )
    assert inside.mean() < 120
    assert in_box.mean() > 0.98


def test_photos_and_scans_come_in_the_planned_formats():
    seen = [augment.capture(_page(600, 850), seed, {})[1] for seed in range(40)]
    assert {c.mode for c in seen} == {"photo", "scanner"}
    assert {c.format for c in seen if c.mode == "photo"} == {"jpeg"}
    assert {c.format for c in seen if c.mode == "scanner"} == {"jpeg", "png", "pdf"}
    assert all(c.jpeg_quality is None for c in seen if c.format == "png")


@pytest.mark.parametrize(
    "value", [dt.date(2026, 6, 11), dt.date(2026, 12, 31), dt.date(2026, 1, 1)]
)
def test_handwritten_dates_read_back_as_the_date(value):
    for seed in range(8):
        text = handwriting.date_text(value, random.Random(seed))
        day, month, year = text.split(".")
        assert (int(day), int(month)) == (value.day, value.month)
        assert int(year) in (value.year, value.year % 100)


def test_the_note_is_where_its_boxes_say_and_nowhere_else():
    case = next(c for c in dataset_cases() if c.id == "seed-01-zse-electricity-ocu")
    for seed in range(6):
        page = Image.new("RGB", (2481, 3509), "white")
        note = handwriting.draw_note(page, case.invoice, seed)
        assert note.date is not None and note.number is not None
        assert note.number.text == case.invoice.handwritten.number
        ink = np.argwhere(np.asarray(page.convert("L")) < 200)
        box = note.box()
        assert box is not None
        inside = (
            (ink[:, 0] >= box.y0)
            & (ink[:, 0] < box.y1)
            & (ink[:, 1] >= box.x0)
            & (ink[:, 1] < box.x1)
        )
        assert inside.all()
        assert box.y1 < 3509 * 0.25  # in the top quarter


def test_an_unreadable_item_of_the_note_is_left_out():
    case = next(c for c in dataset_cases() if c.id == "heldout-10-bvs-water-ocu-noise")
    note = handwriting.draw_note(Image.new("RGB", (2481, 3509), "white"), case.invoice, 1)
    assert note.date is None and note.number is not None and note.number.text == "239"


def test_the_stamp_is_drawn_in_three_of_four_pages():
    drawn = [handwriting.draw_stamp(Image.new("RGB", (2481, 3509), "white"), s) for s in range(40)]
    assert 20 <= sum(box is not None for box in drawn) <= 38
