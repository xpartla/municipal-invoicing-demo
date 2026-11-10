"""Seeded capture damage (plan §8.6): the clean 300-dpi page as a phone photo or a scan.

A photo: the page on a darker background, turned up to ±3° with a little perspective, warm
paper, uneven light, blur, noise, JPEG, 90–130 dpi; like the four anchors. A scan: almost
straight, white surroundings, less noise, sometimes grayscale, 100–150 dpi, PNG, JPEG or PDF.

Everything comes from the seed through numpy's PCG64 and `random.Random`, and Pillow encodes
without timestamps (the PDF's dates are fixed), so the same seed gives the same bytes.
"""

import io
import math
import random
import time
from collections.abc import Mapping

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageFilter

from riso.testdata.truth import Box, Capture

FIXED_TIME = time.strptime("2026-01-01", "%Y-%m-%d")  # Pillow's PDF dates take a struct_time
SOURCE_DPI = 300

Corners = list[tuple[float, float]]


def _homography(src: Corners, dst: Corners) -> NDArray[np.float64]:
    """The 3×3 projective map taking the four `src` points to the four `dst` points."""
    rows = []
    for (x, y), (u, v) in zip(src, dst, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.asarray(rows, dtype=np.float64))
    matrix: NDArray[np.float64] = vt[-1].reshape(3, 3)
    normalised: NDArray[np.float64] = matrix / matrix[2, 2]
    return normalised


def _apply(matrix: NDArray[np.float64], x: float, y: float) -> tuple[float, float]:
    u, v, w = matrix @ np.array([x, y, 1.0])
    return float(u / w), float(v / w)


def map_box(box: Box, scale: float, matrix: NDArray[np.float64], size: tuple[int, int]) -> Box:
    """Where a box of the clean page lies in the capture: its corners scaled and mapped, the
    smallest upright box around them, inside the image."""
    corners = [(box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1)]
    mapped = [_apply(matrix, x * scale, y * scale) for x, y in corners]
    xs = [p[0] for p in mapped]
    ys = [p[1] for p in mapped]
    return Box(
        x0=max(0, math.floor(min(xs))),
        y0=max(0, math.floor(min(ys))),
        x1=min(size[0], math.ceil(max(xs))),
        y1=min(size[1], math.ceil(max(ys))),
    )


def _background(rng: np.random.Generator, size: tuple[int, int], photo: bool) -> Image.Image:
    """What surrounds the page: a table or a sofa in a photo, the scanner's lid in a scan."""
    if photo:
        base = rng.uniform(55, 125) * np.array(
            [1.0, rng.uniform(0.85, 1.0), rng.uniform(0.7, 0.95)]
        )
        texture = rng.normal(0, 12, (12, 16, 1)) + rng.normal(0, 2, (12, 16, 3))
    else:
        base = np.full(3, rng.uniform(236, 250))
        texture = rng.normal(0, 2, (12, 16, 1)) + np.zeros((12, 16, 3))
    small = np.clip(base + texture, 0, 255).astype(np.uint8)
    return Image.fromarray(small, "RGB").resize(size, Image.Resampling.BICUBIC)


def capture(
    page: Image.Image, seed: int, boxes: Mapping[str, Box]
) -> tuple[bytes, Capture, dict[str, Box]]:
    """The page (RGB, 300 dpi) captured with the seed's damage: the file's bytes, what was
    done, and where each of `boxes` (in the clean page's pixels) is in the capture."""
    choose = random.Random(seed)
    rng = np.random.default_rng(seed)
    photo = choose.random() < 0.6
    dpi = choose.randint(90, 130) if photo else choose.randint(100, 150)
    scale = dpi / SOURCE_DPI

    small = page.resize(
        (round(page.width * scale), round(page.height * scale)), Image.Resampling.LANCZOS
    )
    w, h = small.size

    # The page in the capture: margins around it, turned about the centre, the corners moved.
    margin = (0.02, 0.05) if photo else (0.004, 0.015)
    left, right = (choose.uniform(*margin) * w for _ in range(2))
    top, bottom = (choose.uniform(*margin) * h for _ in range(2))
    size = (round(w + left + right), round(h + top + bottom))
    angle = math.radians(choose.uniform(-3, 3) if photo else choose.uniform(-1.2, 1.2))
    cx, cy = size[0] / 2, size[1] / 2
    jitter = choose.uniform(0.004, 0.015) * w if photo else 0.0
    straight = [(left, top), (left + w, top), (left + w, top + h), (left, top + h)]
    turned = _turned(straight, angle, cx, cy)
    dst: Corners = [
        (x + choose.uniform(-jitter, jitter), y + choose.uniform(-jitter, jitter))
        for x, y in turned
    ]
    src: Corners = [(0, 0), (w, 0), (w, h), (0, h)]
    forward = _homography(src, dst)
    inverse = np.linalg.inv(forward)
    coefficients = tuple(float(c) for c in (inverse / inverse[2, 2]).flatten()[:8])

    # Paper colour and light, on the page before it is placed.
    pixels = np.asarray(small, dtype=np.float32)
    if photo:
        tint = np.array(
            [choose.uniform(0.93, 0.99), choose.uniform(0.91, 0.97), choose.uniform(0.85, 0.93)]
        )
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        lx, ly = choose.uniform(0, w), choose.uniform(0, h)
        falloff = choose.uniform(0.04, 0.16)
        light = 1 - falloff * (((xs - lx) / w) ** 2 + ((ys - ly) / h) ** 2)
        pixels = pixels * tint * light[..., None]
    else:
        pixels = pixels * choose.uniform(0.97, 1.0)
    paper = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), "RGB")

    placed = paper.transform(
        size, Image.Transform.PERSPECTIVE, coefficients, Image.Resampling.BICUBIC
    )
    mask = Image.new("L", small.size, 255).transform(
        size, Image.Transform.PERSPECTIVE, coefficients, Image.Resampling.BILINEAR
    )
    image = Image.composite(placed, _background(rng, size, photo), mask)

    blur = choose.uniform(0.3, 1.0) if photo else choose.uniform(0.0, 0.5)
    if blur > 0.05:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    noise = choose.uniform(3, 8) if photo else choose.uniform(1, 4)
    noisy = np.asarray(image, dtype=np.float32) + rng.normal(0, noise, (size[1], size[0], 3))
    image = Image.fromarray(np.clip(noisy, 0, 255).round().astype(np.uint8), "RGB")
    grayscale = not photo and choose.random() < 0.5
    if grayscale:
        image = image.convert("L")

    fmt = "jpeg" if photo else choose.choice(("png", "jpeg", "pdf", "pdf"))
    quality = choose.randint(60, 88) if fmt in ("jpeg", "pdf") else None
    data = _encode(image, fmt, dpi, quality)

    moved = max(math.dist(a, b) for a, b in zip(dst, turned, strict=True))
    info = Capture(
        mode="photo" if photo else "scanner",
        format=fmt,
        dpi=dpi,
        width=size[0],
        height=size[1],
        grayscale=grayscale,
        rotation=round(math.degrees(angle), 3),
        perspective=round(moved, 2),
        blur=round(blur, 3),
        noise=round(noise, 3),
        jpeg_quality=quality,
        page=[(round(x, 2), round(y, 2)) for x, y in dst],
    )
    return data, info, {name: map_box(box, scale, forward, size) for name, box in boxes.items()}


def _turned(points: Corners, angle: float, cx: float, cy: float) -> Corners:
    """The points turned counter-clockwise by `angle` (radians) about (cx, cy)."""
    cos, sin = math.cos(angle), math.sin(angle)
    return [
        (cx + (x - cx) * cos + (y - cy) * sin, cy - (x - cx) * sin + (y - cy) * cos)
        for x, y in points
    ]


def _encode(image: Image.Image, fmt: str, dpi: int, quality: int | None) -> bytes:
    out = io.BytesIO()
    if fmt == "png":
        image.save(out, "PNG", dpi=(dpi, dpi), optimize=False)
    elif fmt == "jpeg":
        image.save(out, "JPEG", quality=quality, dpi=(dpi, dpi), optimize=False)
    else:
        # A scanner's PDF: the page as a JPEG image (the quality reaches Pillow's JPEG
        # encoder), no text layer.
        image.save(
            out,
            "PDF",
            resolution=float(dpi),
            quality=quality,
            title="scan",
            producer="riso testdata",
            creator="riso testdata",
            creationDate=FIXED_TIME,
            modDate=FIXED_TIME,
        )
    return out.getvalue()
