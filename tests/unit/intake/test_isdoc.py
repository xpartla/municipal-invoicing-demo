"""Reading ISDOC (P2-M6-T04): every synthetic ISDOC file, on its own and inside its PDF,
maps to its case's document; and the reader as the extraction will use it."""

from decimal import Decimal

import pytest
from lxml import etree

from riso.intake.domain.einvoice import EInvoiceFormat
from riso.intake.domain.layout import ReadingFailed
from riso.intake.infrastructure.xml.reader import embedded_einvoice, read_einvoice
from riso.testdata.einvoices import (
    attach,
    blank_pdf,
    expected_document,
    isdoc_invoice,
    isdoc_pdf,
    ubl_invoice,
)
from riso.testdata.scans import dataset_cases
from tests.unit.intake.test_ubl import NOT_COMPARED, differences

CASES = dataset_cases()
BY_ID = {case.id: case for case in CASES}
ISDOC = "http://isdoc.cz/namespace/2013"
NS = {"i": ISDOC}


def edited(case_id: str, edit) -> bytes:
    case = BY_ID[case_id]
    root = etree.fromstring(isdoc_invoice(case.invoice, case.id))
    edit(root)
    return etree.tostring(root)


def compare(document, case) -> list[str]:
    expected = expected_document(case.invoice, "isdoc")
    return differences(
        document.model_dump(exclude=NOT_COMPARED), expected.model_dump(exclude=NOT_COMPARED)
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_every_synthetic_isdoc_file_maps_to_its_case(case):
    reading = read_einvoice(isdoc_invoice(case.invoice, case.id))
    assert reading.format is EInvoiceFormat.ISDOC
    assert reading.schema_errors == ()
    assert compare(reading.document, case) == []


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_every_synthetic_isdoc_pdf_maps_to_its_case(case):
    found = embedded_einvoice(isdoc_pdf(case.invoice, case.id))
    assert found is not None
    reading, xml = found
    assert xml == isdoc_invoice(case.invoice, case.id)
    assert reading.attachment is not None and reading.attachment.endswith(".isdoc")
    assert reading.intake_format == "isdoc_pdf"
    assert compare(reading.document, case) == []


def test_the_isdoc_reads_every_line_amount():
    document = read_einvoice(isdoc_invoice(*_zse())).document
    line = document.lines[0]
    assert (line.net, line.vat_rate, line.vat, line.gross) == (
        Decimal("172.24"),
        Decimal(23),
        Decimal("39.62"),
        Decimal("211.86"),
    )
    assert (line.quantity, line.unit, line.unit_price) == (Decimal(1240), "kWh", Decimal("0.1389"))
    assert (
        document.supplier.dic == "2020285512" and document.invoice.variable_symbol == "7101834526"
    )
    assert document.intake is not None and document.intake.format == "isdoc"
    assert set(document.ocr_meta.confidence.values()) == {1.0}


def _zse():
    case = BY_ID["seed-01-zse-electricity-ocu"]
    return case.invoice, case.id


def test_a_credit_note_reads_negative():
    case = BY_ID["seed-21-zse-credit-note"]
    reading = read_einvoice(isdoc_invoice(case.invoice, case.id))
    assert reading.document.invoice.document_type == "credit_note"
    assert reading.document.totals.gross == Decimal("-52.27")
    assert reading.document.lines[0].quantity == Decimal(-210)


def test_a_document_without_vat_reads_gross_only():
    case = BY_ID["seed-12-zmos-membership"]
    document = read_einvoice(isdoc_invoice(case.invoice, case.id)).document
    assert document.supplier.vat_payer is False
    assert (document.totals.net, document.totals.vat, document.totals.vat_rates) == (None, None, [])
    assert all((ln.net, ln.vat, ln.vat_rate) == (None, None, None) for ln in document.lines)


def test_a_czech_vat_number_is_not_a_slovak_dic():
    def czech(root):
        party = root.find("i:AccountingSupplierParty/i:Party", NS)
        for scheme in party.findall("i:PartyTaxScheme", NS):
            party.remove(scheme)
        tax = etree.SubElement(party, f"{{{ISDOC}}}PartyTaxScheme")
        etree.SubElement(tax, f"{{{ISDOC}}}CompanyID").text = "CZ25596641"
        etree.SubElement(tax, f"{{{ISDOC}}}TaxScheme").text = "VAT"

    supplier = read_einvoice(edited("seed-01-zse-electricity-ocu", czech)).document.supplier
    assert (supplier.ic_dph, supplier.dic, supplier.vat_payer) == ("CZ25596641", None, True)


def test_a_schema_error_is_reported_and_the_invoice_still_read():
    def no_uuid(root):
        root.remove(root.find("i:UUID", NS))

    reading = read_einvoice(edited("seed-01-zse-electricity-ocu", no_uuid))
    assert len(reading.schema_errors) == 1 and "IssueDate" in reading.schema_errors[0]
    assert reading.document.totals.gross == Decimal("322.67")


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"<Invoice xmlns='urn:example'/>", "einvoice_unknown"),
        (b"<Invoice", "xml_invalid"),
        (b'<!DOCTYPE x [<!ENTITY e "e">]><x/>', "xml_dtd"),
    ],
)
def test_xml_that_is_not_an_e_invoice_fails(data, reason):
    with pytest.raises(ReadingFailed) as failed:
        read_einvoice(data)
    assert failed.value.reason == reason


def test_an_isdoc_without_a_total_fails():
    def no_total(root):
        monetary = root.find("i:LegalMonetaryTotal", NS)
        monetary.find("i:TaxInclusiveAmount", NS).text = ""

    with pytest.raises(ReadingFailed) as failed:
        read_einvoice(edited("seed-01-zse-electricity-ocu", no_total))
    assert failed.value.reason == "einvoice_no_total"


def test_a_pdf_takes_its_first_known_e_invoice_and_skips_the_rest():
    case = BY_ID["seed-01-zse-electricity-ocu"]
    cii = (
        b'<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:'
        b'CrossIndustryInvoice:100"/>'
    )
    pdf = attach(
        attach(attach(blank_pdf(), "factur-x.xml", cii), "bad.xml", b"<a"),
        "f.xml",
        ubl_invoice(case.invoice),
    )
    found = embedded_einvoice(pdf)
    assert found is not None
    assert found[0].format is EInvoiceFormat.UBL_INVOICE
    assert found[0].intake_format == "ubl_pdf"


def test_a_pdf_without_an_e_invoice_is_none():
    cii = b'<rsm:X xmlns:rsm="urn:example"/>'
    assert embedded_einvoice(blank_pdf()) is None
    assert embedded_einvoice(attach(blank_pdf(), "factur-x.xml", cii)) is None
