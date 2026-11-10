"""Preparing pages for OCR (P2-M5-T04, plan §8.2 step 1): upscaled to about 300 dpi,
grayscale, contrast, straightened; and refusing decompression bombs."""

import struct
import zlib

import pypdfium2 as pdfium
import pytest
from PIL import Image

from riso.intake.domain import MediaType
from riso.intake.domain.layout import ReadingFailed
from riso.intake.infrastructure.imaging import load_pages, prepare_pages
from riso.intake.infrastructure.normalise import normalise, skew_angle
from riso.testdata.scans import SAMPLES_DIR

DIGITAL = SAMPLES_DIR / "heldout-07-hornbach-kd.digital.pdf"


def _clean_page(dpi: int) -> Image.Image:
    """A sample's digital PDF rendered as a straight page."""
    page = pdfium.PdfDocument(DIGITAL.read_bytes())[0]
    return page.render(scale=dpi / 72).to_pil().convert("RGB")


@pytest.mark.parametrize("turn", [2.5, -1.5, 0.8, -3.0])
def test_a_skewed_page_is_straightened(turn):
    skewed = _clean_page(150).rotate(
        turn, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white"
    )
    assert abs(skew_angle(skewed) + turn) <= 0.3
    result = normalise(skewed, 150)
    assert abs(result.angle + turn) <= 0.3
    assert abs(skew_angle(result.image)) <= 0.3


def test_a_low_resolution_page_is_upscaled_to_300_dpi_in_grayscale():
    result = normalise(_clean_page(100), 100)
    assert result.image.mode == "L"
    assert result.dpi == 300 and result.scale == pytest.approx(3.0)
    assert abs(result.image.width - 2480) <= 12


def test_a_300_dpi_page_keeps_its_size():
    page = _clean_page(300)
    result = normalise(page, 300)
    assert result.scale == 1.0 and result.angle == 0.0 and result.image.size == page.size


def test_contrast_is_stretched():
    faded = _clean_page(150).point(lambda v: 90 + v * 0.5)  # dark grey on light grey
    low, high = normalise(faded, 150).image.getextrema()
    assert low <= 10 and high >= 245


def _png_header(width: int, height: int) -> bytes:
    """A PNG claiming a size, with no real image: Pillow judges the size from the header."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\x00"))
        + chunk(b"IEND", b"")
    )


@pytest.mark.parametrize("side", [10_000, 30_000])
def test_a_decompression_bomb_is_refused(side):
    with pytest.raises(ReadingFailed) as refused:
        load_pages(_png_header(side, side), MediaType.PNG)
    assert refused.value.reason == "too_many_pixels"


def test_a_pdf_page_too_large_to_render_is_refused():
    pdf = pdfium.PdfDocument.new()
    pdf.new_page(14_400, 14_400)  # 200 inches square
    out = __import__("io").BytesIO()
    pdf.save(out)
    with pytest.raises(ReadingFailed) as refused:
        load_pages(out.getvalue(), MediaType.PDF)
    assert refused.value.reason == "too_many_pixels"


def test_prepared_pages_are_normalised_and_say_how():
    [page] = prepare_pages(DIGITAL.read_bytes(), MediaType.PDF, "a" * 64)
    assert page.image.mode == "L" and page.dpi == 300 and page.scale == 1.0
