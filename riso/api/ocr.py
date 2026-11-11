"""The OCR commands of the CLI (`riso ocr setup`, `riso ocr record`), here because they wire
the intake context's adapters: the Tesseract models, and the recorded layouts the fast tests
and the E2E journeys replay (plan §8.3, decision 63)."""

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

from riso.intake.domain import MediaType, sniff
from riso.intake.infrastructure.handwriting import InkLocator
from riso.intake.infrastructure.imaging import prepare_pages
from riso.intake.infrastructure.recorded import RECORDINGS_DIR, RecordedReader
from riso.intake.infrastructure.tesseract import TesseractReader, setup_models


def setup_ocr_models(tessdata: Path) -> list[tuple[str, str]]:
    return setup_models(tessdata)


def record_layouts(files: Iterable[Path], tessdata: Path, out: Path | None = None) -> int:
    """Reads each file's pages with Tesseract, as the extraction prepares them, and stores the
    layouts for `RecordedReader` with the digits pass of each first page's note, replacing
    the directory's recordings. Returns how many pages were recorded."""
    directory = out or RECORDINGS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    for stale in directory.glob("*.json"):
        stale.unlink()
    reader = TesseractReader(tessdata)
    recorder = RecordedReader(directory)
    locator = InkLocator()
    count = 0
    try:
        for path in files:
            data = path.read_bytes()
            media_type = sniff(data)
            if not isinstance(media_type, MediaType):
                raise RuntimeError(f"{path.name} is not a document the intake takes")
            for page in prepare_pages(data, media_type, hashlib.sha256(data).hexdigest()):
                layout = reader.read(page)
                recorder.record(page, layout)
                count += 1
                if page.index == 0:  # the note's digits pass, as the extraction makes it
                    region = locator.locate(page.image, layout)
                    for box in region.groups or (region.box,):
                        recorder.record(page, reader.read_digits(page, box), box)
        (directory / "engine.json").write_text(
            json.dumps({"engine": reader.engine, "version": reader.version}, indent=2) + "\n"
        )
    finally:
        reader.close()
    return count
