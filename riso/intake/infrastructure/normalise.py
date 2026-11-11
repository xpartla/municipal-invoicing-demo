"""Preparing a page for OCR (plan §8.2 step 1, §8.1 conclusion 1): grayscale, upscaled to
about 300 dpi (Tesseract needs it: the four anchor photos are about 90 dpi), autocontrast, and
straightened by the angle of its text lines, its dark bars inverted (white text on dark is
lost to Tesseract). The result is the page the check step shows, so the words' boxes are in
its pixels. A page whose words come from a text layer is only made grayscale and contrasted.

The angle comes from the projection profile: on a small binarised copy, the turn under which
the rows of ink are sharpest (their sums vary most) is the text's angle; it is looked for
within ±5° in quarter degrees, then refined to a twentieth of a degree.
"""

from collections import deque
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageOps

TARGET_DPI = 300
UPSCALE_BELOW = 250
"""Pages under this resolution are upscaled to `TARGET_DPI`."""
MAX_SIDE = 5000
"""A page is never made larger than this on its longer side."""
MAX_ANGLE = 5.0
_PROFILE_WIDTH = 900


@dataclass(frozen=True, slots=True)
class Normalised:
    image: Image.Image
    dpi: int
    scale: float
    """How much the page was enlarged."""
    angle: float
    """Degrees it was turned (counter-clockwise) to straighten its lines."""


def _sharpness(ink: npt.NDArray[np.bool_]) -> float:
    rows = ink.sum(axis=1, dtype=np.float64)
    return float(np.var(np.diff(rows)))


def skew_angle(image: Image.Image) -> float:
    """The angle (degrees, counter-clockwise) that straightens the page's text lines."""
    gray = image.convert("L")
    factor = _PROFILE_WIDTH / gray.width
    small = gray.resize(
        (_PROFILE_WIDTH, max(1, round(gray.height * factor))), Image.Resampling.BILINEAR
    )
    pixels = np.asarray(small, dtype=np.uint8)
    threshold = min(200, int(pixels.mean() - pixels.std()))
    binary = Image.fromarray(((pixels < threshold) * 255).astype(np.uint8), "L")

    def score(angle: float) -> float:
        turned = binary.rotate(angle, resample=Image.Resampling.NEAREST, fillcolor=0)
        return _sharpness(np.asarray(turned) > 0)

    coarse = [a / 4 for a in range(int(-MAX_ANGLE * 4), int(MAX_ANGLE * 4) + 1)]
    best = max(coarse, key=score)
    fine = [best + a / 20 for a in range(-5, 6)]
    angle: float = max(fine, key=score)
    return round(angle, 2)


def normalise(image: Image.Image, dpi: int, *, for_ocr: bool = True) -> Normalised:
    gray = image.convert("L")
    scale = 1.0
    if dpi < UPSCALE_BELOW:
        scale = TARGET_DPI / dpi
    longest = max(gray.size) * scale
    if longest > MAX_SIDE:
        scale = MAX_SIDE / max(gray.size)
    if abs(scale - 1.0) > 0.01:
        gray = gray.resize(
            (round(gray.width * scale), round(gray.height * scale)), Image.Resampling.LANCZOS
        )
    else:
        scale = 1.0
    gray = ImageOps.autocontrast(gray, cutoff=1)
    angle = skew_angle(gray) if for_ocr else 0.0
    if abs(angle) >= 0.1:
        gray = gray.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    else:
        angle = 0.0
    if for_ocr:
        inverted, _ = invert_bars(np.asarray(gray), dpi=round(dpi * scale))
        gray = Image.fromarray(inverted)
    return Normalised(gray, round(dpi * scale), scale, angle)


# Dark bars ----------------------------------------------------------------------------------

BAR_BLOCK = 8
BAR_DARK = 110


def invert_bars(
    gray: npt.NDArray[np.uint8], *, dpi: int = 300
) -> tuple[npt.NDArray[np.uint8], int]:
    """Dark bars and boxes with white text (a bill's "SUMA NA ÚHRADU", a payment box)
    inverted, so Tesseract reads them, and how many were: on a grid of 8-px blocks, the
    blocks mostly dark are joined into regions; a region at least a text line tall that
    fills most of its box and does not touch the image's edge (a photo's surroundings) has
    its box inverted. White letters make only small holes in a region; the white gap
    between two stacked bars separates them."""
    height, width = gray.shape
    block = max(4, round(BAR_BLOCK * dpi / 300))
    rows, cols = height // block, width // block
    dark = gray[: rows * block, : cols * block] < BAR_DARK
    filled = dark.reshape(rows, block, cols, block).mean(axis=(1, 3)) >= 0.5
    seen = np.zeros_like(filled)
    out = gray.copy()
    count = 0
    min_rows = max(3, round(25 * dpi / 300 / block))
    min_cols = max(4, round(width * 0.06 / block))
    for r0, c0 in zip(*np.nonzero(filled), strict=True):
        if seen[r0, c0]:
            continue
        queue = deque([(int(r0), int(c0))])
        seen[r0, c0] = True
        top, left, bottom, right, cells = int(r0), int(c0), int(r0), int(c0), 0
        while queue:
            r, c = queue.popleft()
            cells += 1
            top, left, bottom, right = min(top, r), min(left, c), max(bottom, r), max(right, c)
            for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if 0 <= nr < rows and 0 <= nc < cols and filled[nr, nc] and not seen[nr, nc]:
                    seen[nr, nc] = True
                    queue.append((nr, nc))
        tall, wide = bottom - top + 1, right - left + 1
        at_edge = top == 0 or left == 0 or bottom >= rows - 1 or right >= cols - 1
        if tall < min_rows or wide < min_cols or at_edge:
            continue
        if cells / (tall * wide) < 0.6 or tall * wide > 0.25 * rows * cols:
            continue
        y0, y1, x0, x1 = top * block, (bottom + 1) * block, left * block, (right + 1) * block
        out[y0:y1, x0:x1] = 255 - out[y0:y1, x0:x1]
        count += 1
    return out, count
