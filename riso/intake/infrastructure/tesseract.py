"""Tesseract as the `DocumentReader` (plan §8.2 step 2, §8.3): LSTM models `slk+eng` from
`tessdata_best`, words with boxes, line and block numbers and confidences from Tesseract's TSV
output.

The page segmentation is 11 (sparse text), not the plan's 3 (automatic): on the committed
samples mode 3 dropped framed blocks (a boxed recapitulation with the total, a table's
amounts), and the extractor finds more fields in mode 11's fragments, which it joins by
position (P2-M5-T05; the measurement is in the log).

Tesseract runs in a pool of one process started with `spawn` (never `fork` from a process
with threads), so a long page never holds the API's process; the process keeps one
initialised engine for every page it reads. `riso ocr setup` fetches the pinned models into
`RISO_TESSDATA` and checks their SHA-256.
"""

import concurrent.futures
import csv
import hashlib
import io
import multiprocessing
import os
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from PIL import Image

from riso.intake.application.ports import PageImage
from riso.intake.domain.layout import Box, PageLayout, ReadingFailed, Word

LANGUAGES = "slk+eng"
MODELS_TAG = "4.1.0"
"""The `tessdata_best` release (tag 4.1.0, commit e2aad9b)."""
MODELS_URL = (
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/{tag}/{lang}.traineddata"
)


@dataclass(frozen=True, slots=True)
class Model:
    language: str
    sha256: str
    size: int

    def path(self, tessdata: Path) -> Path:
        return tessdata / f"{self.language}.traineddata"


MODELS = (
    Model("slk", "3553e335f64408412c8741fec19e443b5fda81d88abe59aa1401cba4e8825bed", 11_542_252),
    Model("eng", "8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba", 15_400_601),
)
READ_TIMEOUT = 120.0
"""Seconds one page may take before the read is given up."""


def models_ready(tessdata: Path) -> bool:
    """Whether every model is in place with its size (the hash is checked by the setup)."""
    return all(
        m.path(tessdata).is_file() and m.path(tessdata).stat().st_size == m.size for m in MODELS
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - a pinned https URL
        data: bytes = response.read()
        return data


def setup_models(tessdata: Path, fetch: Callable[[str], bytes] = _fetch) -> list[tuple[str, str]]:
    """Puts the pinned models into `tessdata`: (language, `present` | `downloaded`). A file
    whose hash differs is fetched again; a download whose hash differs is refused
    (`RuntimeError`) and nothing is written."""
    tessdata.mkdir(parents=True, exist_ok=True)
    done = []
    for model in MODELS:
        target = model.path(tessdata)
        if target.is_file() and _sha256(target) == model.sha256:
            done.append((model.language, "present"))
            continue
        data = fetch(MODELS_URL.format(tag=MODELS_TAG, lang=model.language))
        if hashlib.sha256(data).hexdigest() != model.sha256:
            raise RuntimeError(f"the {model.language} model's SHA-256 is not the pinned one")
        handle, temporary = tempfile.mkstemp(dir=tessdata, prefix=f".{model.language}-")
        with os.fdopen(handle, "wb") as out:
            out.write(data)
        os.replace(temporary, target)
        done.append((model.language, "downloaded"))
    return done


# --- in the OCR process -----------------------------------------------------------------------

_ENGINE: Any = None


def _engine(tessdata: str) -> Any:
    global _ENGINE
    if _ENGINE is None:
        import tesserocr

        _ENGINE = tesserocr.PyTessBaseAPI(
            path=tessdata,
            lang=LANGUAGES,
            psm=tesserocr.PSM.SPARSE_TEXT,
            oem=tesserocr.OEM.LSTM_ONLY,
        )
    return _ENGINE


def _tsv(tessdata: str, image: Image.Image, dpi: int, digits: bool) -> str:
    """Runs in the OCR process: the page's words as Tesseract's TSV."""
    engine = _engine(tessdata)
    import tesserocr

    if digits:
        engine.SetPageSegMode(tesserocr.PSM.SINGLE_BLOCK)
        engine.SetVariable("tessedit_char_whitelist", "0123456789./")
    try:
        engine.SetImage(image)
        engine.SetSourceResolution(dpi)
        tsv: str = engine.GetTSVText(0)
        return tsv
    finally:
        if digits:
            engine.SetPageSegMode(tesserocr.PSM.SPARSE_TEXT)
            engine.SetVariable("tessedit_char_whitelist", "")


def _version() -> str:
    import tesserocr

    return str(tesserocr.tesseract_version().split()[1])


# --- in the app -------------------------------------------------------------------------------


def shifted(layout: PageLayout, region: Box, page: PageImage) -> PageLayout:
    """A crop's layout in the page's pixels."""
    words = tuple(
        replace(
            w,
            box=Box(
                w.box.x0 + region.x0,
                w.box.y0 + region.y0,
                w.box.x1 + region.x0,
                w.box.y1 + region.y0,
            ),
        )
        for w in layout.words
    )
    return replace(layout, width=page.image.width, height=page.image.height, words=words)


def parse_tsv(tsv: str, *, index: int, width: int, height: int, dpi: int) -> PageLayout:
    """Tesseract's TSV (level 5 rows are words) as a `PageLayout`. Lines are numbered on
    the page by (block, paragraph, line); words without text are dropped."""
    words = []
    lines: dict[tuple[int, int, int], int] = {}
    reader = csv.reader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    for row in reader:
        if len(row) < 12 or row[0] != "5":
            continue
        text = row[11].strip()
        if not text:
            continue
        block, paragraph, line = int(row[2]), int(row[3]), int(row[4])
        left, top, w, h = (int(v) for v in row[6:10])
        number = lines.setdefault((block, paragraph, line), len(lines))
        confidence = round(max(0.0, min(1.0, float(row[10]) / 100)), 4)
        words.append(Word(text, Box(left, top, left + w, top + h), confidence, block, number))
    return PageLayout(index=index, width=width, height=height, dpi=dpi, words=tuple(words))


class TesseractReader:
    engine = "tesseract"

    def __init__(self, tessdata: Path, *, in_process: bool = False) -> None:
        self._tessdata = tessdata
        self._in_process = in_process
        self._pool: concurrent.futures.ProcessPoolExecutor | None = None
        self._version: str | None = None

    @property
    def version(self) -> str:
        """Tesseract's version and the models': `5.5.3 tessdata_best 4.1.0`."""
        if self._version is None:
            self._version = f"{self._call(_version)} tessdata_best {MODELS_TAG}"
        return self._version

    def read(self, page: PageImage) -> PageLayout:
        image = page.image
        tsv = self._call(_tsv, str(self._tessdata), image, page.dpi, False)
        return parse_tsv(
            tsv, index=page.index, width=image.width, height=image.height, dpi=page.dpi
        )

    def read_digits(self, page: PageImage, region: Box) -> PageLayout:
        crop = page.image.crop((region.x0, region.y0, region.x1, region.y1))
        tsv = self._call(_tsv, str(self._tessdata), crop, page.dpi, True)
        read = parse_tsv(tsv, index=page.index, width=crop.width, height=crop.height, dpi=page.dpi)
        return shifted(read, region, page)

    def _call(self, function: Callable[..., Any], *args: Any) -> Any:
        if not models_ready(self._tessdata):
            raise ReadingFailed("no_models", "the OCR models are missing: run riso ocr setup")
        if self._in_process:
            return function(*args)
        try:
            return self._executor().submit(function, *args).result(timeout=READ_TIMEOUT)
        except concurrent.futures.TimeoutError:
            self.close()
            raise ReadingFailed("ocr_timeout", "reading the page took too long") from None
        except concurrent.futures.process.BrokenProcessPool:
            self.close()
            raise ReadingFailed("ocr_failed", "the OCR process stopped") from None

    def _executor(self) -> concurrent.futures.ProcessPoolExecutor:
        if self._pool is None:
            self._pool = concurrent.futures.ProcessPoolExecutor(
                max_workers=1, mp_context=multiprocessing.get_context("spawn")
            )
        return self._pool

    def close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None
