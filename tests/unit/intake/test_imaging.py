import io

import pytest
from PIL import Image

from riso.intake.domain import MediaType
from riso.intake.domain.layout import ReadingFailed
from riso.intake.infrastructure.imaging import load_pages, prepare_pages


def _encoded(fmt: str, size=(400, 560), frames: int = 1, **options) -> bytes:
    out = io.BytesIO()
    pages = [Image.new("RGB", size, "white") for _ in range(frames)]
    pages[0].save(out, fmt, save_all=frames > 1, append_images=pages[1:], **options)
    return out.getvalue()


def test_pdf_pages_are_rendered_at_300_dpi():
    data = _encoded("PDF", size=(595, 842), frames=2, resolution=72.0)  # A4 in points
    pages = load_pages(data, MediaType.PDF)
    assert len(pages) == 2
    image, dpi = pages[0]
    assert dpi == 300 and image.mode == "RGB"
    assert abs(image.width - 2479) <= 2 and abs(image.height - 3508) <= 2


def test_an_image_keeps_its_stated_resolution_else_is_taken_as_a4():
    [(_, stated)] = load_pages(_encoded("PNG", dpi=(150, 150)), MediaType.PNG)
    [(_, guessed)] = load_pages(_encoded("JPEG", size=(827, 1170)), MediaType.JPEG)
    assert stated == 150 and guessed == 100


def test_exif_orientation_is_applied():
    image = Image.new("RGB", (600, 400), "white")
    exif = image.getexif()
    exif[0x0112] = 6  # rotated 90° clockwise when shown
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    [(upright, _)] = load_pages(out.getvalue(), MediaType.JPEG)
    assert upright.size == (400, 600)


def test_a_tiff_gives_one_page_per_frame_up_to_five():
    assert len(load_pages(_encoded("TIFF", frames=3), MediaType.TIFF)) == 3
    with pytest.raises(ReadingFailed) as many:
        load_pages(_encoded("TIFF", frames=6), MediaType.TIFF)
    assert many.value.reason == "too_many_pages"


@pytest.mark.parametrize(
    ("data", "media_type"),
    [
        (b"%PDF-1.4\n garbage", MediaType.PDF),
        (b"\xff\xd8\xff\xe0 truncated", MediaType.JPEG),
        (b"\x89PNG\r\n\x1a\n broken", MediaType.PNG),
    ],
)
def test_a_file_that_will_not_open_says_so(data, media_type):
    with pytest.raises(ReadingFailed) as failed:
        load_pages(data, media_type)
    assert failed.value.reason == "unreadable"


def test_prepared_pages_carry_their_number_and_the_document():
    pages = prepare_pages(_encoded("TIFF", frames=2), MediaType.TIFF, "f" * 64)
    assert [(p.index, p.document_sha256) for p in pages] == [(0, "f" * 64), (1, "f" * 64)]
