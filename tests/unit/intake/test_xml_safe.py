"""Safe XML parsing and format detection (P2-M6-T02, plan §8.4, §12)."""

import pytest
from lxml import etree

from riso.intake.domain.document import starts_as_xml
from riso.intake.domain.einvoice import EInvoiceFormat
from riso.intake.domain.layout import ReadingFailed
from riso.intake.infrastructure.xml import safe
from riso.intake.infrastructure.xml.attachments import xml_attachments
from riso.testdata.einvoices import attach, blank_pdf, isdoc_invoice, isdoc_pdf, ubl_invoice
from riso.testdata.scans import dataset_cases

CASES = {case.id: case for case in dataset_cases()}
INVOICE = CASES["seed-01-zse-electricity-ocu"]
CREDIT_NOTE = CASES["heldout-35-metro-credit-note"]


def _refused(data: bytes) -> str:
    with pytest.raises(ReadingFailed) as refused:
        safe.parse(data)
    return refused.value.reason


def test_an_external_entity_is_refused_and_never_read(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET")
    xxe = (
        f'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file://{secret}">]><r>&x;</r>'
    ).encode()
    assert _refused(xxe) == "xml_dtd"


def test_the_refusal_does_not_depend_on_where_the_doctype_is():
    """A DOCTYPE behind 5 kB of comments, past the quick look at the file's start, is found
    after parsing (which itself resolves nothing)."""
    padding = b"<!--" + b"x" * 5000 + b"-->"
    late = b'<?xml version="1.0"?>' + padding + b'<!DOCTYPE r [<!ENTITY x "boom">]><r>&x;</r>'
    assert _refused(late) == "xml_dtd"


def test_a_billion_laughs_is_refused():
    lol = ['<!ENTITY lol0 "lol">'] + [
        f'<!ENTITY lol{i} "{f"&lol{i - 1};" * 10}">' for i in range(1, 10)
    ]
    bomb = f'<?xml version="1.0"?><!DOCTYPE lolz [{"".join(lol)}]><lolz>&lol9;</lolz>'
    assert _refused(bomb.encode()) == "xml_dtd"


def test_an_external_dtd_is_refused_without_network():
    remote = b'<?xml version="1.0"?><!DOCTYPE r SYSTEM "http://127.0.0.1:9/evil.dtd"><r/>'
    assert _refused(remote) == "xml_dtd"


def test_an_oversized_file_is_refused_before_parsing():
    big = b"<r>" + b" " * safe.MAX_XML_BYTES + b"</r>"
    assert _refused(big) == "xml_too_large"


def test_a_text_node_past_the_parser_limit_is_refused():
    """libxml2 caps a text node at 10 MB without `huge_tree`."""
    huge = b"<r>" + b"a" * (11 * 1024 * 1024) + b"</r>"
    assert _refused(huge) == "xml_invalid"


def test_nesting_past_the_parser_limit_is_refused():
    deep = b"<a>" * 300 + b"</a>" * 300
    assert _refused(deep) == "xml_invalid"


@pytest.mark.parametrize(
    "data", [b"", b"not xml", b"<r>", b"<r></s>", b"\xff\xfe<\x00r\x00/\x00>\x00 garbage"]
)
def test_what_is_not_well_formed_is_refused(data):
    assert _refused(data) == "xml_invalid"


def test_comments_and_processing_instructions_are_dropped():
    root = safe.parse(b'<?xml version="1.0"?><r><!-- note --><?pi x?><a>1</a></r>')
    assert [etree.QName(child).localname for child in root] == ["a"]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (ubl_invoice(INVOICE.invoice), EInvoiceFormat.UBL_INVOICE),
        (ubl_invoice(CREDIT_NOTE.invoice), EInvoiceFormat.UBL_CREDIT_NOTE),
        (isdoc_invoice(INVOICE.invoice, INVOICE.id), EInvoiceFormat.ISDOC),
        (b'<Invoice xmlns="urn:example:other"/>', None),
        (
            b'<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:'
            b'CrossIndustryInvoice:100"/>',
            None,
        ),
        (b"<Invoice/>", None),
    ],
    ids=["ubl-invoice", "ubl-credit-note", "isdoc", "other-namespace", "cii", "no-namespace"],
)
def test_the_format_is_detected_by_root_and_namespace(data, expected):
    assert safe.detect(safe.parse(data)) is expected


def test_the_isdoc_is_found_in_its_pdf():
    pdf = isdoc_pdf(INVOICE.invoice, INVOICE.id)
    [attachment] = xml_attachments(pdf)
    assert attachment.name == "7101834526.isdoc"
    assert attachment.data == isdoc_invoice(INVOICE.invoice, INVOICE.id)


def test_a_pdf_without_xml_attachments_has_none():
    assert xml_attachments(blank_pdf()) == []
    with_image = attach(blank_pdf(), "photo.jpg", b"\xff\xd8\xff\xe0 not xml")
    assert xml_attachments(with_image) == []
    assert xml_attachments(b"%PDF-1.7 damaged") == []


def test_every_xml_attachment_is_listed_in_order():
    pdf = attach(attach(blank_pdf(), "a.xml", b"<a/>"), "b.isdoc", b"\xef\xbb\xbf <b/>")
    assert [a.name for a in xml_attachments(pdf)] == ["a.xml", "b.isdoc"]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b'<?xml version="1.0"?><r/>', True),
        (b"\xef\xbb\xbf\n  <Invoice/>", True),
        (b"<!-- c --><r/>", True),
        (b"%PDF-1.7", False),
        (b"", False),
        (b"< r/>", False),
    ],
)
def test_xml_is_recognised_by_its_first_bytes(data, expected):
    assert starts_as_xml(data) is expected
