"""The note written on an invoice when it arrives (plan §8.1): the booking date and the
sequence number, in ballpoint ink, at the top of the page; and the municipality's blue
approval stamp ("Súhlasím s úhradou") with a signature, lower down.

Drawn with Pillow on the clean 300-dpi page, before the capture damage. A font is easier to
read than a hand, so the handwriting results on this set are optimistic (plan §8.6).
"""

import datetime as dt
import math
import random
from dataclasses import dataclass
from functools import cache

from PIL import Image, ImageDraw, ImageFont

from riso.contracts import InvoiceDocument
from riso.testdata.fonts import HANDWRITING_FONTS, STAMP_FONT, font_path
from riso.testdata.truth import Box, Handwriting, Note

PLACEMENTS = ("split", "stacked", "inline", "margin")


@cache
def _font(relative: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_path(relative)), size)


def date_text(value: dt.date, rng: random.Random) -> str:
    """As people write it on the invoice: `23.6.26`, `11.6.2026`, `01.07.26`."""
    style = rng.choice(("d.m.yy", "d.m.yyyy", "dd.mm.yy", "d.m.yy"))
    year = str(value.year) if style == "d.m.yyyy" else f"{value.year % 100:02d}"
    if style == "dd.mm.yy":
        return f"{value.day:02d}.{value.month:02d}.{year}"
    return f"{value.day}.{value.month}.{year}"


@dataclass(frozen=True, slots=True)
class _Ink:
    rgb: tuple[int, int, int]
    pressure: float

    @classmethod
    def ballpoint(cls, rng: random.Random) -> "_Ink":
        if rng.random() < 0.8:
            rgb = (rng.randint(20, 60), rng.randint(40, 90), rng.randint(140, 195))
        else:
            rgb = (rng.randint(20, 45), rng.randint(20, 45), rng.randint(30, 60))
        return cls(rgb, rng.uniform(0.75, 0.95))


def _written(text: str, font: str, size: int, rng: random.Random) -> Image.Image:
    """The text as an ink mask (mode L, 255 = full ink), cropped to the ink: each character a
    little bigger or smaller and off the baseline, the word slanted and turned."""
    width = int(size * (len(text) + 2))
    mask = Image.new("L", (width, size * 3), 0)
    draw = ImageDraw.Draw(mask)
    x = float(size) / 2
    stroke = rng.choice((0, 1, 1, 2))
    for char in text:
        face = _font(font, max(8, round(size * rng.uniform(0.88, 1.12))))
        y = size * 0.9 + rng.uniform(-0.07, 0.07) * size
        draw.text(
            (x, y), char, font=face, fill=255, anchor="ls", stroke_width=stroke, stroke_fill=255
        )
        x += face.getlength(char) * rng.uniform(0.92, 1.12) + rng.uniform(0, 0.05) * size
    shear = rng.uniform(-0.25, 0.12)
    mask = mask.transform(
        mask.size,
        Image.Transform.AFFINE,
        (1, shear, -shear * mask.height / 2, 0, 1, 0),
        resample=Image.Resampling.BICUBIC,
    )
    mask = mask.rotate(rng.uniform(-7, 7), resample=Image.Resampling.BICUBIC, expand=True)
    bbox = mask.getbbox()
    return mask.crop(bbox) if bbox else mask


def _paste(page: Image.Image, mask: Image.Image, at: tuple[int, int], ink: _Ink) -> Box:
    """Ink `mask` onto the page with its top-left at `at` (clamped inside the page); returns
    where the ink is."""
    x = min(max(0, at[0]), page.width - mask.width - 1)
    y = min(max(0, at[1]), page.height - mask.height - 1)
    alpha = mask.point(lambda v: round(v * ink.pressure))
    page.paste(Image.new("RGB", mask.size, ink.rgb), (x, y), alpha)
    return Box(x0=x, y0=y, x1=x + mask.width, y1=y + mask.height)


def draw_note(page: Image.Image, document: InvoiceDocument, seed: int) -> Handwriting:
    """Write the case's handwritten date and number on the page (RGB, 300 dpi). An item the
    case does not have (unreadable on the original) is left out."""
    rng = random.Random(seed)
    font = rng.choice(HANDWRITING_FONTS)
    placement = rng.choice(PLACEMENTS)
    ink = _Ink.ballpoint(rng)
    w, h = page.size
    size = rng.randint(70, 110)
    written = document.handwritten
    date_str = date_text(written.date, rng) if written.date else None
    date_mask = _written(date_str, font, size, rng) if date_str else None
    number = written.number
    number_mask = (
        _written(number, font, round(size * rng.uniform(0.95, 1.15)), rng) if number else None
    )
    top = int(h * rng.uniform(0.008, 0.035))

    date_at = number_at = (0, 0)
    if placement == "split":
        date_at = (int(w * rng.uniform(0.3, 0.55)), top)
        number_at = (int(w * rng.uniform(0.82, 0.9)), int(h * rng.uniform(0.008, 0.035)))
    elif placement == "stacked":
        date_at = (int(w * rng.uniform(0.68, 0.8)), top)
        gap = int(size * rng.uniform(0.15, 0.4))
        below = top + (date_mask.height if date_mask else size) + gap
        number_at = (date_at[0] + int(size * rng.uniform(0, 1.2)), below)
    elif placement == "inline":
        date_at = (int(w * rng.uniform(0.08, 0.45)), top)
        width = date_mask.width if date_mask else size * 4
        number_at = (date_at[0] + width + int(w * rng.uniform(0.03, 0.09)), top)
    else:  # margin: the date at the top, the number down the right margin
        date_at = (int(w * rng.uniform(0.3, 0.6)), top)
        number_at = (int(w * rng.uniform(0.9, 0.93)), int(h * rng.uniform(0.05, 0.12)))

    date_note = number_note = None
    if date_mask is not None and date_str is not None:
        date_note = Note(text=date_str, box=_paste(page, date_mask, date_at, ink))
    if number_mask is not None and number is not None:
        number_note = Note(text=number, box=_paste(page, number_mask, number_at, ink))
    return Handwriting(font=font, placement=placement, date=date_note, number=number_note)


def draw_stamp(page: Image.Image, seed: int) -> Box | None:
    """The approval stamp with a signature, in three of four cases; returns where it is."""
    rng = random.Random(seed)
    if rng.random() >= 0.75:
        return None
    w, h = page.size
    size = rng.randint(48, 62)
    face = _font(STAMP_FONT, size)
    layer = Image.new("L", (size * 14, size * 4), 0)
    draw = ImageDraw.Draw(layer)
    draw.text((size // 2, size // 3), "Súhlasím s úhradou", font=face, fill=255)
    draw.text((size // 2, int(size * 1.9)), "Podpis " + "." * 22, font=face, fill=255)
    # The signature: a scribble across the dotted line.
    points = []
    x, y = size * 3.5, size * 2.4
    for i in range(14):
        x += rng.uniform(0.25, 0.6) * size
        y = size * 2.3 + math.sin(i * rng.uniform(1.2, 2.2)) * size * 0.7
        points.append((x, y))
    draw.line(points, fill=255, width=rng.randint(3, 5), joint="curve")
    layer = layer.rotate(rng.uniform(-9, 9), resample=Image.Resampling.BICUBIC, expand=True)
    bbox = layer.getbbox()
    layer = layer.crop(bbox) if bbox else layer
    ink = _Ink(
        (rng.randint(30, 60), rng.randint(60, 95), rng.randint(160, 200)), rng.uniform(0.55, 0.8)
    )
    at = (int(w * rng.uniform(0.18, 0.45)), int(h * rng.uniform(0.5, 0.75)))
    return _paste(page, layer, at, ink)
