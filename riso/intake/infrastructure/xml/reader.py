"""The e-invoice reader (plan §8.4): an XML file, or a PDF carrying one, to an
`EInvoiceReading` with its XSD findings. It implements the application's `EInvoiceReader`.

An XML file that cannot be parsed, is neither UBL nor ISDOC, or has no supplier or total
fails the reading (`ReadingFailed`, decision 65). A PDF is an e-invoice when one of its
attachments is: the first that parses and is UBL or ISDOC is taken; a PDF without one
(Factur-X's CII included) is read as an ordinary PDF.
"""

from collections.abc import Callable
from dataclasses import replace

from lxml import etree

from riso.intake.domain.einvoice import EInvoiceFormat, EInvoiceReading, require_essentials
from riso.intake.domain.layout import ReadingFailed
from riso.intake.infrastructure.xml import safe
from riso.intake.infrastructure.xml.attachments import xml_attachments
from riso.intake.infrastructure.xml.isdoc import read_isdoc
from riso.intake.infrastructure.xml.schemas import schema_errors
from riso.intake.infrastructure.xml.ubl import read_ubl

_READERS: dict[EInvoiceFormat, Callable[[etree._Element, EInvoiceFormat], EInvoiceReading]] = {
    EInvoiceFormat.UBL_INVOICE: read_ubl,
    EInvoiceFormat.UBL_CREDIT_NOTE: read_ubl,
    EInvoiceFormat.ISDOC: read_isdoc,
}


def read_einvoice(data: bytes, attachment: str | None = None) -> EInvoiceReading:
    """The XML's reading, or `ReadingFailed` (`xml_*`, `einvoice_unknown`,
    `einvoice_no_supplier`, `einvoice_no_total`)."""
    root = safe.parse(data)
    fmt = safe.detect(root)
    if fmt is None:
        raise ReadingFailed("einvoice_unknown")
    reading = _READERS[fmt](root, fmt)
    require_essentials(reading.document)
    return replace(reading, schema_errors=tuple(schema_errors(root, fmt)), attachment=attachment)


def embedded_einvoice(pdf: bytes) -> tuple[EInvoiceReading, bytes] | None:
    """The e-invoice attached to the PDF, with its XML; None when it has none."""
    for found in xml_attachments(pdf):
        try:
            root = safe.parse(found.data)
        except ReadingFailed:
            continue
        if safe.detect(root) is not None:
            return read_einvoice(found.data, attachment=found.name), found.data
    return None


class XmlEInvoiceReader:
    """The adapter of the `EInvoiceReader` port."""

    def read_xml(self, data: bytes) -> EInvoiceReading:
        return read_einvoice(data)

    def read_pdf(self, data: bytes) -> tuple[EInvoiceReading, bytes] | None:
        return embedded_einvoice(data)
