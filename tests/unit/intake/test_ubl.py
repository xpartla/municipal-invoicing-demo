"""Reading UBL (P2-M6-T03): every synthetic UBL file maps to its case's document, field by
field, and the reader finds the fields in the places real files use too."""

from decimal import Decimal

import pytest
from lxml import etree

from riso.intake.domain.einvoice import EInvoiceFormat
from riso.intake.infrastructure.xml import safe
from riso.intake.infrastructure.xml.ubl import read_ubl
from riso.testdata.einvoices import expected_document, ubl_invoice
from riso.testdata.scans import dataset_cases

CASES = dataset_cases()
BY_ID = {case.id: case for case in CASES}
NOT_COMPARED = {"id", "ocr_meta", "intake"}
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
NS = {"cac": CAC, "cbc": CBC}


def differences(got: object, expected: object, path: str = "") -> list[str]:
    """Every field where the two dumps differ, as `path: got != expected`."""
    if isinstance(got, dict) and isinstance(expected, dict):
        return [
            d
            for key in sorted(set(got) | set(expected))
            for d in differences(got.get(key), expected.get(key), f"{path}.{key}")
        ]
    if isinstance(got, list) and isinstance(expected, list) and len(got) == len(expected):
        return [
            d
            for i, (g, e) in enumerate(zip(got, expected, strict=True))
            for d in differences(g, e, f"{path}[{i}]")
        ]
    return [] if got == expected else [f"{path}: {got!r} != {expected!r}"]


def read(data: bytes):
    root = safe.parse(data)
    fmt = safe.detect(root)
    assert fmt is not None
    return read_ubl(root, fmt)


def edited(case_id: str, edit) -> bytes:
    root = etree.fromstring(ubl_invoice(BY_ID[case_id].invoice))
    edit(root)
    return etree.tostring(root)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_every_synthetic_ubl_file_maps_to_its_case(case):
    reading = read(ubl_invoice(case.invoice))
    got = reading.document.model_dump(exclude=NOT_COMPARED)
    expected = expected_document(case.invoice, "ubl").model_dump(exclude=NOT_COMPARED)
    assert differences(got, expected) == []


def test_the_comparison_sees_a_wrong_field():
    data = edited(
        "seed-01-zse-electricity-ocu",
        lambda r: r.find("cac:PaymentMeans/cbc:PaymentID", NS).__setattr__("text", "123"),
    )
    got = read(data).document.model_dump(exclude=NOT_COMPARED)
    case = BY_ID["seed-01-zse-electricity-ocu"]
    expected = expected_document(case.invoice, "ubl").model_dump(exclude=NOT_COMPARED)
    assert differences(got, expected) == [".invoice.variable_symbol: '123' != '7101834526'"]


def test_every_field_read_is_trusted_and_the_channel_is_einvoice():
    reading = read(ubl_invoice(BY_ID["seed-01-zse-electricity-ocu"].invoice))
    document = reading.document
    assert document.intake is not None
    assert (document.intake.channel, document.intake.format) == ("einvoice", "ubl")
    confidence = document.ocr_meta.confidence
    assert set(confidence.values()) == {1.0}
    assert {"supplier.ico", "supplier.iban", "invoice.variable_symbol", "totals.gross"} <= set(
        confidence
    )
    assert "lines[0].description" in confidence and "lines[0].gross" not in confidence
    assert reading.version == "2.1"
    assert reading.profile is not None and "peppol" in reading.profile


def test_a_credit_note_reads_negative():
    reading = read(ubl_invoice(BY_ID["heldout-35-metro-credit-note"].invoice))
    document = reading.document
    assert reading.format is EInvoiceFormat.UBL_CREDIT_NOTE
    assert document.invoice.document_type == "credit_note"
    assert document.totals.gross == Decimal("-44.94")
    assert document.lines[0].quantity == Decimal(-24) and document.lines[0].unit_price > 0
    assert reading.payable == Decimal("-44.94")


def test_an_invoice_with_a_credit_note_type_code_is_a_credit_note():
    def as_381(root):
        root.find("cbc:InvoiceTypeCode", NS).text = "381"

    reading = read(edited("seed-01-zse-electricity-ocu", as_381))
    assert reading.format is EInvoiceFormat.UBL_INVOICE
    assert reading.document.invoice.document_type == "credit_note"
    assert reading.document.totals.gross == Decimal("-322.67")


def test_the_ico_is_also_found_in_the_party_identification():
    def move_ico(root):
        party = root.find("cac:AccountingSupplierParty/cac:Party", NS)
        legal = party.find("cac:PartyLegalEntity", NS)
        legal.remove(legal.find("cbc:CompanyID", NS))
        identification = etree.Element(f"{{{CAC}}}PartyIdentification")
        etree.SubElement(identification, f"{{{CBC}}}ID", schemeID="0158").text = "35823551"
        party.insert(1, identification)

    assert read(edited("seed-01-zse-electricity-ocu", move_ico)).document.supplier.ico == "35823551"


def test_the_dic_is_read_off_the_ic_dph_without_an_endpoint():
    def drop_endpoint(root):
        party = root.find("cac:AccountingSupplierParty/cac:Party", NS)
        party.remove(party.find("cbc:EndpointID", NS))

    supplier = read(edited("seed-01-zse-electricity-ocu", drop_endpoint)).document.supplier
    assert (supplier.dic, supplier.ic_dph) == ("2020285512", "SK2020285512")


def test_an_endpoint_of_another_scheme_is_not_a_dic():
    def vat_endpoint(root):
        endpoint = root.find("cac:AccountingSupplierParty/cac:Party/cbc:EndpointID", NS)
        endpoint.set("schemeID", "9950")
        endpoint.text = "SK2020285599"

    # The IČ DPH still gives the DIČ; the 9950 endpoint is not taken for it.
    supplier = read(edited("seed-01-zse-electricity-ocu", vat_endpoint)).document.supplier
    assert supplier.dic == "2020285512"


@pytest.mark.parametrize(
    ("payment_id", "expected"),
    [
        ("7101834526", "7101834526"),
        ("VS7101834526/SS123", "7101834526"),
        ("RF18539007547034", None),
    ],
)
def test_the_variable_symbol_is_the_payment_reference(payment_id, expected):
    def set_id(root):
        root.find("cac:PaymentMeans/cbc:PaymentID", NS).text = payment_id

    header = read(edited("seed-01-zse-electricity-ocu", set_id)).document.invoice
    assert header.variable_symbol == expected


def test_a_price_per_base_quantity_is_a_unit_price():
    def per_hundred(root):
        price = root.find("cac:InvoiceLine/cac:Price", NS)
        price.find("cbc:PriceAmount", NS).text = "13.89"
        etree.SubElement(price, f"{{{CBC}}}BaseQuantity", unitCode="KWH").text = "100"

    line = read(edited("seed-01-zse-electricity-ocu", per_hundred)).document.lines[0]
    assert line.unit_price == Decimal("0.1389")
    assert line.unit == "kWh"


def test_a_supplier_outside_vat_has_gross_amounts_only():
    document = read(ubl_invoice(BY_ID["seed-12-zmos-membership"].invoice)).document
    assert document.supplier.vat_payer is False
    assert (document.totals.net, document.totals.vat) == (None, None)
    assert document.totals.gross == Decimal("61.20")
    assert all(line.net is None and line.gross is not None for line in document.lines)


def test_exempt_lines_have_no_rate_but_keep_their_net():
    document = read(ubl_invoice(BY_ID["heldout-06-telekom-fees"].invoice)).document
    rated, exempt = document.lines[0], document.lines[1]
    assert rated.vat_rate == Decimal(23) and exempt.vat_rate is None
    assert exempt.net == Decimal("10.00")
    assert document.totals.vat_rates == [Decimal(23)]


def test_a_minimal_invoice_reads_what_it_has():
    minimal = """<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
      xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
      xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
      <cbc:ID>F1</cbc:ID><cbc:IssueDate>2026-05-04</cbc:IssueDate>
      <cac:AccountingSupplierParty><cac:Party><cac:PartyName><cbc:Name>Dodávateľ s.r.o.</cbc:Name>
      </cac:PartyName></cac:Party></cac:AccountingSupplierParty>
      <cac:LegalMonetaryTotal><cbc:PayableAmount currencyID="EUR">12.30</cbc:PayableAmount>
      </cac:LegalMonetaryTotal></Invoice>""".encode()
    document = read(minimal).document
    assert document.supplier.name == "Dodávateľ s.r.o."
    assert (document.supplier.ico, document.supplier.iban, document.supplier.vat_payer) == (
        None,
        None,
        None,
    )
    assert document.totals.gross == Decimal("12.30")
    assert document.invoice.currency == "EUR" and document.lines == []


def test_the_checks_flag_exactly_what_the_cases_carry():
    """The dataset's noise cases carry their defects into the e-invoice too; every other case
    passes every check."""
    from riso.intake.domain.einvoice import check

    flagged = {}
    for case in CASES:
        warnings = check(read(ubl_invoice(case.invoice)).document, customer_ico="00305863")
        if warnings:
            flagged[case.id] = warnings
    assert flagged == {
        "heldout-04-vzorova-accounting": ("missing_iban", "missing_variable_symbol"),
        "heldout-16-ozpomoc-noise": ("supplier_ico_check_digit",),
        "heldout-17-slovnaft-noise": ("missing_supplier_ico",),
        "heldout-26-fcc-waste-noise": ("totals_do_not_add_up",),
        "heldout-35-metro-credit-note": ("missing_due_date",),
    }
