"""OCR tests need the models (`riso ocr setup`); the `ocr` CI job fetches them. Without them
the tests fail and say so: a skipped OCR run would look like a passed one."""

import pytest

from riso.intake.infrastructure.tesseract import TesseractReader, models_ready
from riso.platform.settings import Settings


@pytest.fixture(scope="session")
def tessdata():
    path = Settings().tessdata
    assert path is not None
    if not models_ready(path):
        pytest.fail(f"no OCR models in {path}: run `uv run riso ocr setup`")
    return path


@pytest.fixture(scope="session")
def tesseract(tessdata):
    reader = TesseractReader(tessdata)
    yield reader
    reader.close()
