"""`RecordedReader` (plan §8.3): replays layouts Tesseract made earlier, so the extractor's
tests and the E2E journeys run fast, the same everywhere, and without the models (plan §2
decision 63). A recording is `<document sha256>-<page>.json` (a `PageLayout`) in its
directory, next to `engine.json` naming the engine that made them; `riso ocr record` writes
them from the committed samples."""

import json
from pathlib import Path

from riso.intake.application.ports import PageImage
from riso.intake.domain.layout import Box, PageLayout, ReadingFailed

RECORDINGS_DIR = Path(__file__).resolve().parents[3] / "testdata" / "ocr" / "recorded"


def recording_name(document_sha256: str, index: int, region: Box | None = None) -> str:
    """`<sha256>-<page>.json`, and for a digits pass `<sha256>-<page>-digits-<box>.json`."""
    if region is None:
        return f"{document_sha256}-{index}.json"
    box = "-".join(str(v) for v in region.to_list())
    return f"{document_sha256}-{index}-digits-{box}.json"


class RecordedReader:
    engine = "recorded"

    def __init__(self, directory: Path = RECORDINGS_DIR) -> None:
        self._directory = directory

    @property
    def version(self) -> str:
        """The engine that made the recordings: `tesseract 5.5.3 tessdata_best 4.1.0`."""
        meta = self._directory / "engine.json"
        if not meta.is_file():
            return "unknown"
        data = json.loads(meta.read_text())
        return f"{data['engine']} {data['version']}"

    def read(self, page: PageImage) -> PageLayout:
        path = self._directory / recording_name(page.document_sha256, page.index)
        if not path.is_file():
            raise ReadingFailed("no_recording", "no recorded layout for this page")
        return PageLayout.from_json(json.loads(path.read_text()))

    def read_digits(self, page: PageImage, region: Box) -> PageLayout:
        path = self._directory / recording_name(page.document_sha256, page.index, region)
        if not path.is_file():
            raise ReadingFailed("no_recording", "no recorded layout for this region")
        return PageLayout.from_json(json.loads(path.read_text()))

    def record(self, page: PageImage, layout: PageLayout, region: Box | None = None) -> Path:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / recording_name(page.document_sha256, page.index, region)
        path.write_text(json.dumps(layout.to_json(), ensure_ascii=False, separators=(",", ":")))
        return path
