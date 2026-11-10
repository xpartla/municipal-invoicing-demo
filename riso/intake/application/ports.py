"""The intake context's ports: what its use cases need from the outside."""

from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from riso.intake.domain import MediaType
from riso.intake.domain.layout import PageLayout


class PageCounter(Protocol):
    def pages(self, data: bytes, media_type: MediaType) -> int | None:
        """How many pages the file has: a PDF's pages, a TIFF's frames, 1 for an image.
        None when the file cannot be opened; its extraction then says why."""
        ...


@dataclass(frozen=True, slots=True)
class PageImage:
    """One normalised page of a document, ready to be read."""

    image: Image.Image
    index: int
    """The page's number in the document, from 0."""
    dpi: int
    document_sha256: str
    """The document's content: what recorded layouts are kept by."""
    scale: float = 1.0
    """How much the file's page was enlarged to make this one (plan §8.2 step 1)."""
    angle: float = 0.0
    """Degrees it was turned (counter-clockwise) to straighten its lines."""


class DocumentReader(Protocol):
    """An OCR engine (plan §8.3): `TesseractReader`, `RecordedReader` in tests and E2E, an
    Azure Document Intelligence adapter in phase 2.5."""

    @property
    def engine(self) -> str: ...

    @property
    def version(self) -> str: ...

    def read(self, page: PageImage) -> PageLayout:
        """The page's words. Raises `ReadingFailed` with the reason when it cannot."""
        ...


class TextLayer(Protocol):
    def read(self, data: bytes) -> list[PageLayout] | None:
        """A digital PDF's words from its text layer, every page's; None when a page has no
        usable text layer (a scan), so the document is read by OCR."""
        ...


class PagePreparer(Protocol):
    def prepare(
        self, data: bytes, media_type: MediaType, sha256: str, *, straighten: bool = True
    ) -> list[PageImage]:
        """The document's pages, ready to be read. Raises `ReadingFailed` with the reason
        (`unreadable`, `too_many_pages`, `too_many_pixels`) when the file will not open."""
        ...
