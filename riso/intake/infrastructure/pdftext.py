"""A digital PDF's text layer (plan §8.2, "Digital PDFs"): when a page has enough text, its
words and boxes come from pypdfium2 instead of OCR, exactly as printed (confidence 1). The
boxes are in the pixels of the page rendered at 300 dpi, the image the check step shows.

Characters come in the content stream's order. A word ends at a space, at a line break, at
a gap between the inks wider than 15% of the font's height where the fonts' boxes do not touch
(small print's spaces are narrow), or at a gap of a third of it between the boxes. A line ends
at a line break or when the next character's baseline moves by more than half its height.
"""

from collections.abc import Iterator

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from riso.intake.domain.layout import Box, PageLayout, Word
from riso.intake.infrastructure.imaging import RENDER_DPI

MIN_CHARACTERS = 80
"""A page with fewer visible characters has no usable text layer (a scan with a few
scanner-added words, a blank page)."""
_SCALE = RENDER_DPI / 72


def _characters(
    textpage: pdfium.PdfTextPage, height: float
) -> Iterator[tuple[str, Box | None, tuple[int, int]]]:
    """Each character with its loose box (the font's height, for lines) and its tight left
    and right edges (the ink, for the gaps between words); a space has no box."""
    for index in range(textpage.count_chars()):
        char = textpage.get_text_range(index, 1)
        if not char or char.isspace():
            yield char or " ", None, (0, 0)
            continue
        left, bottom, right, top = textpage.get_charbox(index, loose=True)
        ink_left, _, ink_right, _ = textpage.get_charbox(index, loose=False)
        box = Box(
            round(left * _SCALE),
            round((height - top) * _SCALE),
            round(right * _SCALE),
            round((height - bottom) * _SCALE),
        )
        yield char, box, (round(ink_left * _SCALE), round(ink_right * _SCALE))


def page_words(page: pdfium.PdfPage, index: int) -> PageLayout:
    width, height = page.get_size()
    textpage = page.get_textpage()
    try:
        words: list[Word] = []
        chars: list[tuple[str, Box]] = []
        last_ink = 0
        line = 0

        def flush() -> None:
            if chars:
                text = "".join(c for c, _ in chars)
                box = Box.around(b for _, b in chars)
                assert box is not None
                words.append(Word(text, box, 1.0, 0, line))
                chars.clear()

        for char, box, ink in _characters(textpage, height):
            if box is None:
                flush()
                if char in "\r\n":
                    line += 1 if words and words[-1].line == line else 0
                continue
            if chars:
                last = chars[-1][1]
                size = max(last.height, box.height, 1)
                if abs(box.y1 - last.y1) > size * 0.5:
                    flush()
                    line += 1
                elif (ink[0] - last_ink > size * 0.15 and box.x0 - last.x1 > size * 0.08) or (
                    box.x0 - last.x1 > size / 3
                ):
                    flush()
            chars.append((char, box))
            last_ink = ink[1]
        flush()
    finally:
        textpage.close()
    return PageLayout(
        index=index,
        width=round(width * _SCALE),
        height=round(height * _SCALE),
        dpi=RENDER_DPI,
        words=tuple(words),
        source="text_layer",
    )


def text_layer(data: bytes) -> list[PageLayout] | None:
    """Every page's words, when each page has a usable text layer; else None (OCR it)."""
    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError:
        return None
    try:
        pages = []
        for index, page in enumerate(document):
            layout = page_words(page, index)
            if sum(len(w.text) for w in layout.words) < MIN_CHARACTERS:
                return None
            pages.append(layout)
        return pages
    finally:
        document.close()


def scanned(data: bytes) -> bool:
    """Whether the first page is a scan with a text layer on top (a scanner's searchable
    PDF): an image covers most of it. A billing system's PDF has none."""
    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError:
        return False
    try:
        page = document[0]
        width, height = page.get_size()
        for image in page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,)):
            left, bottom, right, top = image.get_bounds()
            if (right - left) * (top - bottom) >= 0.8 * width * height:
                return True
        return False
    finally:
        document.close()


class PdfTextLayer:
    """The `TextLayer` port."""

    def read(self, data: bytes) -> list[PageLayout] | None:
        return text_layer(data)

    def scanned(self, data: bytes) -> bool:
        return scanned(data)
