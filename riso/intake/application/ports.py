"""The intake context's ports: what its use cases need from the outside."""

from typing import Protocol

from riso.intake.domain import MediaType


class PageCounter(Protocol):
    def pages(self, data: bytes, media_type: MediaType) -> int | None:
        """How many pages the file has: a PDF's pages, a TIFF's frames, 1 for an image.
        None when the file cannot be opened; its extraction then says why."""
        ...
