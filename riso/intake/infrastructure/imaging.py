"""A document's pages as images (plan §8.2 step 1): PDF pages rendered at 300 dpi with
pypdfium2, the frames of a TIFF, a JPEG or PNG with its EXIF orientation applied. Pillow's
decompression-bomb limit stays on, and no more than `MAX_PAGES` pages are read.

`normalise.py` (P2-M5-T04) prepares each page for OCR on top of this.
"""

import io
import warnings

import pypdfium2 as pdfium
from PIL import Image, ImageOps, ImageSequence

from riso.intake.application.ports import PageImage
from riso.intake.domain import MAX_PAGES, MediaType
from riso.intake.domain.layout import ReadingFailed

RENDER_DPI = 300
A4_WIDTH_INCHES = 8.27


def _guess_dpi(image: Image.Image) -> int:
    """The image's resolution: as the file states it when plausible, else as if the page
    were A4 across its width (a phone photo has no meaningful resolution)."""
    stated = image.info.get("dpi")
    if stated:
        value = round(float(stated[0]))
        if 50 <= value <= 1200:
            return value
    return max(30, round(min(image.size) / A4_WIDTH_INCHES))


def load_pages(data: bytes, media_type: MediaType) -> list[tuple[Image.Image, int]]:
    """Each page as an RGB image with its resolution. Raises `ReadingFailed` when the file
    cannot be opened (`unreadable`), is too large to decode (`too_many_pixels`) or has more
    than `MAX_PAGES` pages (`too_many_pages`)."""
    if media_type is MediaType.PDF:
        return _pdf_pages(data)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            frames: list[tuple[Image.Image, int]] = []
            for frame in ImageSequence.Iterator(image):
                if len(frames) == MAX_PAGES:
                    raise ReadingFailed("too_many_pages", f"more than {MAX_PAGES} pages")
                dpi = _guess_dpi(frame)
                upright = ImageOps.exif_transpose(frame.copy())
                frames.append((upright.convert("RGB"), dpi))
            return frames
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ReadingFailed("too_many_pixels", "the image is too large to read") from None
    except (OSError, ValueError, SyntaxError):
        raise ReadingFailed("unreadable", "the file cannot be opened as an image") from None


def _pdf_pages(data: bytes) -> list[tuple[Image.Image, int]]:
    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError:
        raise ReadingFailed("unreadable", "the file cannot be opened as a PDF") from None
    try:
        if len(document) > MAX_PAGES:
            raise ReadingFailed("too_many_pages", f"more than {MAX_PAGES} pages")
        pages = []
        for page in document:
            width, height = page.get_size()
            limit = Image.MAX_IMAGE_PIXELS
            if limit and width * height * (RENDER_DPI / 72) ** 2 > limit:
                raise ReadingFailed("too_many_pixels", "a page is too large to read")
            bitmap = page.render(scale=RENDER_DPI / 72)
            pages.append((bitmap.to_pil().convert("RGB"), RENDER_DPI))
        return pages
    finally:
        document.close()


def prepare_pages(data: bytes, media_type: MediaType, sha256: str) -> list[PageImage]:
    """The document's pages as the reader gets them. The extraction and `riso ocr record`
    both use this, so recorded layouts match the pages they replay for."""
    return [
        PageImage(image, index=index, dpi=dpi, document_sha256=sha256)
        for index, (image, dpi) in enumerate(load_pages(data, media_type))
    ]


class Pages:
    """The `PagePreparer` port."""

    def prepare(self, data: bytes, media_type: MediaType, sha256: str) -> list[PageImage]:
        return prepare_pages(data, media_type, sha256)
