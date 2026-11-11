"""Counting a file's pages without reading it: pypdfium2 for a PDF (the only PDF parser the
app uses, plan §12), Pillow's header for a TIFF's frames; an XML file has none."""

import io
import warnings

import pypdfium2 as pdfium
from PIL import Image

from riso.intake.domain import MediaType


class FilePages:
    def pages(self, data: bytes, media_type: MediaType) -> int | None:
        if media_type is MediaType.XML:
            return None  # an e-invoice has no pages
        if media_type is MediaType.PDF:
            try:
                document = pdfium.PdfDocument(data)
            except pdfium.PdfiumError:
                return None
            try:
                return len(document)
            finally:
                document.close()
        if media_type is MediaType.TIFF:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(data)) as image:
                        return int(getattr(image, "n_frames", 1))
            except (
                OSError,
                ValueError,
                Image.DecompressionBombWarning,
                Image.DecompressionBombError,
            ):
                return None
        return 1
