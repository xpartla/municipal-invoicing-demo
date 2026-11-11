"""Parsing untrusted XML (plan §8.4 "Parsing", §12): lxml with entity resolution, DTD
loading and network access off, and limits on the size of the file, of its text nodes and of
its depth (libxml2's defaults without `huge_tree`). A document with a DOCTYPE is refused
outright, whatever it declares: an e-invoice has none, and refusing it closes external
entities (XXE) and entity expansion ("billion laughs") at once.

A refusal is a `ReadingFailed` whose reason the check step explains: `xml_too_large`,
`xml_dtd`, `xml_invalid`.
"""

from lxml import etree

from riso.intake.domain.einvoice import ROOTS, EInvoiceFormat
from riso.intake.domain.layout import ReadingFailed

MAX_XML_BYTES = 20 * 1024 * 1024
"""An e-invoice is at most as large as an upload (an embedded PDF in base64 included)."""

_DOCTYPE_MARKERS = (b"<!DOCTYPE", b"<!ENTITY")


def _parser() -> etree.XMLParser:
    # A parser per call: lxml parsers keep state and are not shared between threads.
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
    )


def parse(data: bytes) -> etree._Element:
    """The document's root element, or `ReadingFailed`."""
    if len(data) > MAX_XML_BYTES:
        raise ReadingFailed("xml_too_large")
    head = data[:4096].upper()
    if any(marker in head for marker in _DOCTYPE_MARKERS):
        raise ReadingFailed("xml_dtd")
    try:
        root = etree.fromstring(data, _parser())
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise ReadingFailed("xml_invalid") from exc
    tree = root.getroottree()
    if tree.docinfo.doctype or tree.docinfo.internalDTD is not None:
        raise ReadingFailed("xml_dtd")
    return root


def detect(root: etree._Element) -> EInvoiceFormat | None:
    """The format by the root's namespace and name; None for any other XML."""
    name = etree.QName(root)
    return ROOTS.get((name.namespace or "", name.localname))
