"""The synthetic e-invoices (P2-M6-T01): every generated file validates against its XSD, the
same input gives the same bytes, and the committed samples are what the generator writes."""

import hashlib
import json
from decimal import Decimal

import pypdfium2
import pytest
from lxml import etree

from riso.intake.domain.einvoice import EInvoiceFormat
from riso.intake.infrastructure.xml.schemas import schema_errors
from riso.testdata import einvoices
from riso.testdata.einvoices import (
    SAMPLES,
    SAMPLES_DIR,
    case_files,
    isdoc_invoice,
    isdoc_pdf,
    split_address,
    tax_category,
    ubl_invoice,
)
from riso.testdata.scans import dataset_cases

CASES = dataset_cases()


def _ubl_format(case):
    credit = case.invoice.invoice.document_type == "credit_note"
    return EInvoiceFormat.UBL_CREDIT_NOTE if credit else EInvoiceFormat.UBL_INVOICE


def _attachments(pdf_data: bytes) -> list[tuple[str, bytes]]:
    pdf = pypdfium2.PdfDocument(pdf_data)
    found = []
    for i in range(pdf.count_attachments()):
        attachment = pdf.get_attachment(i)
        found.append((attachment.get_name(), bytes(attachment.get_data())))
    return found


def test_there_are_seventy_cases_and_two_credit_notes():
    assert len(CASES) == 70
    assert sum(c.invoice.invoice.document_type == "credit_note" for c in CASES) == 2


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_every_ubl_file_validates_against_the_ubl_xsd(case):
    root = etree.fromstring(ubl_invoice(case.invoice))
    assert schema_errors(root, _ubl_format(case)) == []
    expected = "CreditNote" if _ubl_format(case) is EInvoiceFormat.UBL_CREDIT_NOTE else "Invoice"
    assert etree.QName(root).localname == expected


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_every_isdoc_file_validates_against_the_isdoc_xsd(case):
    root = etree.fromstring(isdoc_invoice(case.invoice, case.id))
    assert schema_errors(root, EInvoiceFormat.ISDOC) == []


@pytest.mark.parametrize("case", CASES[:5] + CASES[-5:], ids=lambda c: c.id)
def test_every_isdoc_pdf_carries_the_isdoc_file(case):
    pdf = isdoc_pdf(case.invoice, case.id)
    [(name, data)] = _attachments(pdf)
    assert name.endswith(".isdoc")
    assert data == isdoc_invoice(case.invoice, case.id)
    assert len(pypdfium2.PdfDocument(pdf)) == 1


def test_the_validator_finds_what_is_wrong():
    case = CASES[0]
    ubl = etree.fromstring(ubl_invoice(case.invoice))
    ubl.remove(ubl.find(f"{{{einvoices._CBC}}}IssueDate"))
    [error] = schema_errors(ubl, EInvoiceFormat.UBL_INVOICE)
    assert "DueDate" in error and "not expected" in error
    isdoc = etree.fromstring(isdoc_invoice(case.invoice, case.id))
    isdoc.find(f"{{{einvoices._ISDOC}}}UUID").text = "not-a-uuid"
    assert any("pattern" in e for e in schema_errors(isdoc, EInvoiceFormat.ISDOC))


def test_the_same_case_gives_the_same_bytes():
    case = next(c for c in CASES if c.id == "heldout-35-metro-credit-note")
    assert case_files(case) == case_files(case)


def test_the_committed_samples_are_what_the_generator_writes():
    """The XML is compared byte for byte; the PDFs (rendered in Chromium) carry the same XML
    and match the manifest."""
    cases = {case.id: case for case in CASES}
    manifest = json.loads((SAMPLES_DIR / "manifest.json").read_text())
    assert manifest["seed"] == 2026
    assert sorted(manifest["cases"]) == sorted(SAMPLES)
    for case_id, files in manifest["cases"].items():
        for name, digest in files.items():
            assert hashlib.sha256((SAMPLES_DIR / name).read_bytes()).hexdigest() == digest, name
        written = case_files(cases[case_id])
        for name in (f"{case_id}.ubl.xml", f"{case_id}.isdoc"):
            assert (SAMPLES_DIR / name).read_bytes() == written[name], name
        pdf = (SAMPLES_DIR / f"{case_id}.isdoc.pdf").read_bytes()
        [(_, data)] = _attachments(pdf)
        assert data == written[f"{case_id}.isdoc"]


def test_the_slovak_identifiers_go_where_peppol_and_isdoc_put_them():
    case = next(c for c in CASES if c.id == "seed-01-zse-electricity-ocu")
    ubl = etree.fromstring(ubl_invoice(case.invoice))
    ns = {"cac": einvoices._CAC, "cbc": einvoices._CBC}
    party = ubl.find("cac:AccountingSupplierParty/cac:Party", ns)
    assert party.findtext("cac:PartyLegalEntity/cbc:CompanyID", namespaces=ns) == "35823551"
    endpoint = party.find("cbc:EndpointID", ns)
    assert (endpoint.text, endpoint.get("schemeID")) == ("2020285512", "0245")
    assert party.findtext("cac:PartyTaxScheme/cbc:CompanyID", namespaces=ns) == "SK2020285512"
    assert ubl.findtext("cac:PaymentMeans/cbc:PaymentID", namespaces=ns) == "7101834526"

    isdoc = etree.fromstring(isdoc_invoice(case.invoice, case.id))
    i = {"i": einvoices._ISDOC}
    party = isdoc.find("i:AccountingSupplierParty/i:Party", i)
    assert party.findtext("i:PartyIdentification/i:ID", namespaces=i) == "35823551"
    schemes = {
        t.findtext("i:TaxScheme", namespaces=i): t.findtext("i:CompanyID", namespaces=i)
        for t in party.findall("i:PartyTaxScheme", i)
    }
    assert schemes == {"VAT": "SK2020285512", "TIN": "2020285512"}
    details = "i:PaymentMeans/i:Payment/i:Details/"
    assert isdoc.findtext(details + "i:VariableSymbol", namespaces=i) == "7101834526"
    assert isdoc.findtext(details + "i:IBAN", namespaces=i) == "SK8011000000002624105532"
    assert isdoc.findtext(details + "i:BankCode", namespaces=i) == "1100"


def test_a_credit_note_is_written_in_positive_amounts():
    case = next(c for c in CASES if c.id == "heldout-35-metro-credit-note")
    assert case.invoice.totals.gross < 0
    ubl = etree.fromstring(ubl_invoice(case.invoice))
    ns = {"cac": einvoices._CAC, "cbc": einvoices._CBC}
    assert ubl.findtext("cac:LegalMonetaryTotal/cbc:PayableAmount", namespaces=ns) == "44.94"
    assert ubl.findtext("cbc:CreditNoteTypeCode", namespaces=ns) == "381"
    isdoc = etree.fromstring(isdoc_invoice(case.invoice, case.id))
    i = {"i": einvoices._ISDOC}
    assert isdoc.findtext("i:DocumentType", namespaces=i) == "2"
    assert isdoc.findtext("i:LegalMonetaryTotal/i:PayableAmount", namespaces=i) == "44.94"


@pytest.mark.parametrize(
    ("text", "street", "zone", "city", "joined"),
    [
        ("Čulenova 6, 816 47 Bratislava", "Čulenova 6", "816 47", "Bratislava", None),
        (
            "Moyzesova 6065/4A, 90201 Pezinok, Slovensko",
            "Moyzesova 6065/4A",
            "90201",
            "Pezinok",
            "Moyzesova 6065/4A, 90201 Pezinok",
        ),
        ("Hlavná 1, Boldog", "Hlavná 1, Boldog", None, None, None),
    ],
)
def test_an_address_splits_into_street_zone_and_city(text, street, zone, city, joined):
    address = split_address(text)
    assert (address.street, address.zone, address.city) == (street, zone, city)
    assert address.text == (joined or text)


def test_a_street_splits_off_its_building_number():
    assert split_address("Moyzesova 6065/4A, 90201 Pezinok").street_and_number() == (
        "Moyzesova",
        "6065/4A",
    )
    assert split_address("Námestie SNP, 811 06 Bratislava").street_and_number() == (
        "Námestie SNP",
        "",
    )


def test_the_tax_category_follows_the_supplier_and_the_line():
    by_id = {c.id: c.invoice for c in CASES}
    zse = by_id["seed-01-zse-electricity-ocu"]
    assert tax_category(zse, zse.lines[0]) == ("S", Decimal(23))
    insurance = by_id["seed-07-kooperativa-vehicle"]
    assert tax_category(insurance, insurance.lines[0]) == ("E", Decimal(0))
    membership = by_id["seed-12-zmos-membership"]
    assert tax_category(membership, membership.lines[0]) == ("O", Decimal(0))
