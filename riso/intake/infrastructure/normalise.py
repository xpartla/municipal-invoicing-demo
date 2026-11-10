"""Preparing a page for OCR (plan §8.2 step 1, §8.1 conclusion 1): grayscale, upscaled to
about 300 dpi (Tesseract needs it: the four anchor photos are about 90 dpi), autocontrast, and
straightened by the angle of its text lines. The result is the page the check step shows, so
the words' boxes are in its pixels.

The angle comes from the projection profile: on a small binarised copy, the turn under which
the rows of ink are sharpest (their sums vary most) is the text's angle; it is looked for
within ±5° in quarter degrees, then refined to a twentieth of a degree.
"""

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


def normalise(image: Image.Image, dpi: int, *, straighten: bool = True) -> Normalised:
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
    angle = skew_angle(gray) if straighten else 0.0
    if abs(angle) >= 0.1:
        gray = gray.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    else:
        angle = 0.0
    return Normalised(gray, round(dpi * scale), scale, angle)
