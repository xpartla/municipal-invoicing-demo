"""Locating the handwritten note (plan §8.1 conclusion 2, §8.2 step 3): ink that is not a
printed word, in the top quarter of the page and its side margins. The crop is kept for the
check step even when nothing in it can be read; when no ink is found, the top band is used.

Printed words are the OCR's words read with some confidence at the size of the page's print
(the median height of its lettered words); handwriting is written larger, so a word much
taller than the print is not masked even when the OCR read it. What ink is left is gathered
on a coarse grid into groups; a group of a handwritten item's size is part of the note. A
group touching the image's edge is the photo's surroundings, not ink.
"""

from collections import deque
from statistics import median

import numpy as np
import numpy.typing as npt
from PIL import Image

from riso.intake.domain.layout import Box, PageLayout, Word
from riso.intake.domain.note import NoteRegion

TOP_SHARE = 0.25
MARGIN_SHARE = 0.08
FALLBACK_SHARE = 0.12
INK_BELOW = 150
"""Grey levels under this are ink (the page is normalised: paper near 255)."""
CELL = 12
"""Grid cell in pixels at 300 dpi."""
RUN = 110
"""Ink in a straight run this long (pixels at 300 dpi) is a rule, a frame or a bar: no
handwritten stroke is that long and straight."""
MIN_FILL = 0.3
"""The share of a group's cells that hold ink; a frame's corner or a stray line holds less."""
TALLER = 1.4
"""A word of digits this much taller than the print is taken for handwriting."""


def print_height(words: tuple[Word, ...]) -> float:
    """The height of the page's print: the median of its confidently read lettered words."""
    heights = [
        w.box.height for w in words if w.confidence >= 0.6 and sum(c.isalpha() for c in w.text) >= 2
    ]
    return float(median(heights)) if heights else 35.0


def is_printed(word: Word, height: float) -> bool:
    """Read with confidence, and either at the print's size or lettered: the note is
    digits and dots, written larger than the print."""
    if word.confidence < 0.5:
        return False
    return word.box.height <= height * TALLER or sum(c.isalpha() for c in word.text) >= 2


def locate(page: Image.Image, layout: PageLayout) -> NoteRegion:
    """`page` is the normalised page (grayscale) the layout was read from."""
    gray = np.asarray(page.convert("L"), dtype=np.uint8)
    height, width = gray.shape
    scale = layout.dpi / 300
    ink = gray < INK_BELOW
    tall = print_height(layout.words)
    grow = max(2, round(4 * scale))
    per_line: dict[int, int] = {}
    for word in layout.words:
        per_line[word.line] = per_line.get(word.line, 0) + 1
    for word in layout.words:
        alone = per_line[word.line] == 1
        if is_printed(word, tall) and not (alone and _note_like(word, tall)):
            b = word.box.grown(grow)
            ink[max(0, b.y0) : max(0, b.y1), max(0, b.x0) : max(0, b.x1)] = False
    region = np.zeros_like(ink)
    region[: round(height * TOP_SHARE), :] = True
    margin = round(width * MARGIN_SHARE)
    region[: height // 2, :margin] = True
    region[: height // 2, width - margin :] = True
    ink &= region
    ink &= ~(_in_runs(ink, round(RUN * scale), 1) | _in_runs(ink, round(RUN * scale), 0))
    cell = max(4, round(CELL * scale))
    groups = [
        (g, fill)
        for g, fill in _groups(ink, cell)
        if not _at_edge(g, width, height, cell) and fill >= MIN_FILL
    ]
    plausible = [
        g
        for g, _ in groups
        if tall * 1.1 <= g.height <= 330 * scale and 30 * scale <= g.width <= 1300 * scale
    ]
    # The note is written above the print, or beside it in a side margin.
    printed = [w.box for w in layout.words if w.confidence >= 0.6 and _lettered(w)]
    first_print = min((b.y0 for b in printed), default=height)
    left = _quantile([b.x0 for b in printed], 0.05, 0)
    right = _quantile([b.x1 for b in printed], 0.95, width)
    above = [
        g
        for g in plausible
        if g.y0 < first_print + tall * 0.5 or g.x1 <= left + tall or g.x0 >= right - tall * 2
    ]
    plausible = above or plausible
    if not plausible:
        return NoteRegion(Box(0, 0, width, round(height * FALLBACK_SHARE)), ())
    box = Box.around(plausible)
    assert box is not None
    pad = round(20 * scale)
    crop = Box(
        max(0, box.x0 - pad),
        max(0, box.y0 - pad),
        min(width, box.x1 + pad),
        min(height, box.y1 + pad),
    )
    return NoteRegion(crop, tuple(sorted(plausible, key=lambda g: (g.y0, g.x0))))


def _in_runs(mask: npt.NDArray[np.bool_], length: int, axis: int) -> npt.NDArray[np.bool_]:
    """The pixels that lie in an unbroken run of at least `length` set pixels along the axis."""
    m = np.moveaxis(mask, axis, -1).astype(np.int32)
    n = m.shape[-1]
    if n < length:
        return np.zeros_like(mask)
    total = np.concatenate([np.zeros((*m.shape[:-1], 1), np.int32), np.cumsum(m, axis=-1)], axis=-1)
    full = (total[..., length:] - total[..., :-length]) == length  # windows wholly inked
    covered = np.concatenate(
        [np.zeros((*full.shape[:-1], 1), np.int32), np.cumsum(full, axis=-1)], axis=-1
    )
    index = np.arange(n)
    start = np.clip(index - length + 1, 0, full.shape[-1])
    stop = np.clip(index + 1, 0, full.shape[-1])
    inside = (covered[..., stop] - covered[..., start]) > 0
    return np.moveaxis(inside, -1, axis)


def _at_edge(box: Box, width: int, height: int, cell: int) -> bool:
    return box.x0 <= cell or box.y0 <= cell or box.x1 >= width - cell or box.y1 >= height - cell


def _note_like(word: Word, height: float) -> bool:
    """Digits and dots, larger than the print: what an item of the note looks like."""
    text = word.text.strip()
    digits = sum(c.isdigit() for c in text)
    return digits >= 1 and digits >= 0.6 * len(text) and word.box.height > height * 1.15


def _quantile(values: list[int], share: float, default: int) -> int:
    if not values:
        return default
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))]


def _lettered(word: Word) -> bool:
    return sum(c.isalpha() for c in word.text) >= 3


def _groups(ink: npt.NDArray[np.bool_], cell: int) -> list[tuple[Box, float]]:
    """Inked cells joined with their neighbours (two cells across, one up or down: a
    handwritten item's characters are apart, its lines are not), as boxes."""
    rows, cols = ink.shape[0] // cell, ink.shape[1] // cell
    if rows == 0 or cols == 0:
        return []
    cells = ink[: rows * cell, : cols * cell].reshape(rows, cell, cols, cell).sum(axis=(1, 3))
    inked = cells >= max(3, cell * cell // 30)
    seen = np.zeros_like(inked)
    found = []
    for r0, c0 in zip(*np.nonzero(inked), strict=True):
        if seen[r0, c0]:
            continue
        queue = deque([(int(r0), int(c0))])
        seen[r0, c0] = True
        top, left, bottom, right = int(r0), int(c0), int(r0), int(c0)
        while queue:
            r, c = queue.popleft()
            top, left, bottom, right = min(top, r), min(left, c), max(bottom, r), max(right, c)
            for dr in (-1, 0, 1):
                for dc in (-2, -1, 0, 1, 2):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols and inked[nr, nc] and not seen[nr, nc]:
                        seen[nr, nc] = True
                        queue.append((nr, nc))
        cells_in_box = (bottom - top + 1) * (right - left + 1)
        fill = float(inked[top : bottom + 1, left : right + 1].sum()) / cells_in_box
        found.append((Box(left * cell, top * cell, (right + 1) * cell, (bottom + 1) * cell), fill))
    return found


def crop(page: Image.Image, box: Box) -> Image.Image:
    return page.crop((box.x0, box.y0, box.x1, box.y1))


class InkLocator:
    """The `NoteLocator` port."""

    def locate(self, page: Image.Image, layout: PageLayout) -> NoteRegion:
        return locate(page, layout)
