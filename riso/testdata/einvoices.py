"""`riso testdata einvoices`: the synthetic e-invoices (plan §8.4, P2-M6-T01, decision 65).

Each of the 70 seed and held-out cases is written in three forms:

- `<case>.ubl.xml`: Peppol BIS Billing 3.0 on UBL 2.1, an `Invoice`, or a `CreditNote` for a
  credit note;
- `<case>.isdoc`: ISDOC 6.0.2;
- `<case>.isdoc.pdf`: the case's digital PDF (the scan set's rendering, without the note)
  with the ISDOC file attached, as Slovak and Czech invoicing tools send it;

and `manifest.json` lists the seed and every file's SHA-256. The XML is plain Python and
fast, so the tests write it as they run; the PDFs need Chromium, like the scans.

Where the Slovak fields go (sources in the P2-M6-T01 log entry):

- UBL: IČO in `PartyLegalEntity/CompanyID`; IČ DPH in `PartyTaxScheme/CompanyID` with the
  `VAT` scheme; DIČ as the Peppol endpoint ID with scheme 0245; VS in `PaymentMeans/PaymentID`;
  IBAN in `PayeeFinancialAccount/ID`; the date of supply in `Delivery/ActualDeliveryDate`.
- ISDOC: IČO in `PartyIdentification/ID`; IČ DPH in `PartyTaxScheme` with `VAT`, DIČ with
  `TIN`; VS in `PaymentMeans/Payment/Details/VariableSymbol`; the date of supply in
  `TaxPointDate`.
- Both write a credit note in positive amounts (ISDOC since 5.2.1, UBL by its CreditNote);
  the reader turns them negative, as the dataset prints them.

A document carries only what its case's `InvoiceDocument` has: an element whose value is
missing is left out where the schema allows it. What a format cannot carry is in
`expected_document`.
"""

import hashlib
import io
import json
import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from lxml import etree

from riso import paths
from riso.contracts import DatasetCase, InvoiceDocument, InvoiceLine
from riso.intake import code_of, unit_of
from riso.testdata.scans import DEFAULT_SEED, SAMPLE_CASES, dataset_cases

GENERATED_DIR = paths.TESTDATA_DIR / "einvoice" / "generated"
SAMPLES_DIR = paths.TESTDATA_DIR / "einvoice" / "samples"

Family = Literal["ubl", "isdoc"]

_UBL_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
_UBL_CREDIT_NOTE = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
_ISDOC = "http://isdoc.cz/namespace/2013"
_CUSTOMIZATION = "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
_PROFILE = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
_SK_DIC = "0245"
_COUNTRY_NAMES = ("Slovensko", "Slovenská republika", "SR")
_ZONE_CITY = re.compile(r"(\d{3} ?\d{2})\s+(.+)")
_BUILDING = re.compile(r"(.*\S)\s+(\d\S*)")
_FIXED_DATE = "D:20260101000000+00'00'"
_TRAILER_ID = re.compile(rb"/ID\s*\[<([0-9A-Fa-f]+)><([0-9A-Fa-f]+)>\]")
_UNSAFE_NAME = re.compile(r"[^\w.-]+")


# --- the parts of a case --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Address:
    street: str
    zone: str | None
    city: str | None

    @property
    def text(self) -> str:
        """As the readers join it: `street, PSČ city`."""
        place = " ".join(p for p in (self.zone, self.city) if p)
        return ", ".join(p for p in (self.street, place) if p)

    def street_and_number(self) -> tuple[str, str]:
        """ISDOC writes the street and the building number apart."""
        match = _BUILDING.fullmatch(self.street)
        return (match.group(1), match.group(2)) if match else (self.street, "")


def split_address(text: str) -> Address:
    """`Čulenova 6, 816 47 Bratislava` into its street, postal zone and city; a trailing
    country name is dropped (both formats give the country as a code)."""
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) > 1 and parts[-1] in _COUNTRY_NAMES:
        parts = parts[:-1]
    if len(parts) > 1 and (match := _ZONE_CITY.fullmatch(parts[-1])):
        return Address(", ".join(parts[:-1]), match.group(1), match.group(2))
    return Address(", ".join(parts), None, None)


def vat_payer(document: InvoiceDocument) -> bool:
    """Whether the supplier charges VAT: printed so, or an IČ DPH."""
    supplier = document.supplier
    return bool(supplier.vat_payer) or supplier.ic_dph is not None


TaxCategory = Literal["S", "E", "O"]


def tax_category(document: InvoiceDocument, line: InvoiceLine) -> tuple[TaxCategory, Decimal]:
    """A line's VAT category (UNCL 5305) and rate: `O` not subject to VAT (the supplier is
    not a payer), `S` at the line's rate, `E` exempt (a payer's line without a rate and
    without VAT: insurance, postage)."""
    if not vat_payer(document):
        return "O", Decimal(0)
    if line.vat_rate is not None:
        return "S", line.vat_rate
    if not line.vat:
        return "E", Decimal(0)
    raise ValueError(f"a line of {document.id} has VAT but no rate")


def _taxable(document: InvoiceDocument, line: InvoiceLine) -> Decimal:
    """The amount a line is taxed on: its net, or its gross when the supplier charges no VAT."""
    category, _ = tax_category(document, line)
    value = line.net if category != "O" else line.gross if line.gross is not None else line.net
    if value is None:
        raise ValueError(f"a line of {document.id} has no amount the format can carry")
    return value


@dataclass(frozen=True, slots=True)
class TaxGroup:
    category: TaxCategory
    rate: Decimal
    taxable: Decimal
    tax: Decimal


def tax_groups(document: InvoiceDocument) -> list[TaxGroup]:
    """The VAT breakdown by category and rate, in the order the lines first use them."""
    groups: dict[tuple[TaxCategory, Decimal], tuple[Decimal, Decimal]] = {}
    for line in document.lines:
        key = tax_category(document, line)
        taxable, tax = groups.get(key, (Decimal(0), Decimal(0)))
        groups[key] = (taxable + _taxable(document, line), tax + (line.vat or Decimal(0)))
    if not groups:
        raise ValueError(f"{document.id} has no lines")
    return [TaxGroup(c, r, taxable, tax) for (c, r), (taxable, tax) in groups.items()]


def _credit(document: InvoiceDocument) -> bool:
    return document.invoice.document_type == "credit_note"


def _money(value: Decimal) -> str:
    return f"{abs(value):.2f}"


def _number(value: Decimal) -> str:
    """A quantity or a unit price as printed: no exponent, no trailing zeros."""
    text = format(abs(value).normalize(), "f")
    return text


def _compact(iban: str) -> str:
    return iban.replace(" ", "")


def _xml(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# --- UBL ------------------------------------------------------------------------------------


class _Ubl:
    def __init__(self, document: InvoiceDocument) -> None:
        self.document = document
        self.credit = _credit(document)
        namespace = _UBL_CREDIT_NOTE if self.credit else _UBL_INVOICE
        self.root = etree.Element(
            f"{{{namespace}}}{'CreditNote' if self.credit else 'Invoice'}",
            nsmap={None: namespace, "cac": _CAC, "cbc": _CBC},
        )

    def cbc(self, parent: etree._Element, name: str, text: str, **attrs: str) -> etree._Element:
        element = etree.SubElement(parent, f"{{{_CBC}}}{name}", attrs)
        element.text = text
        return element

    def cac(self, parent: etree._Element, name: str) -> etree._Element:
        return etree.SubElement(parent, f"{{{_CAC}}}{name}")

    def amount(self, parent: etree._Element, name: str, value: Decimal) -> None:
        self.cbc(parent, name, _money(value), currencyID=self.document.invoice.currency)

    def build(self) -> bytes:
        d = self.document
        root = self.root
        self.cbc(root, "CustomizationID", _CUSTOMIZATION)
        self.cbc(root, "ProfileID", _PROFILE)
        self.cbc(root, "ID", d.invoice.number or d.id)
        if d.invoice.issue_date is None:
            raise ValueError(f"{d.id} has no issue date")
        self.cbc(root, "IssueDate", d.invoice.issue_date.isoformat())
        if not self.credit and d.invoice.due_date is not None:
            self.cbc(root, "DueDate", d.invoice.due_date.isoformat())
        self.cbc(root, "CreditNoteTypeCode" if self.credit else "InvoiceTypeCode",
                 "381" if self.credit else "380")  # fmt: skip
        if d.free_text:
            self.cbc(root, "Note", "\n".join(d.free_text))
        self.cbc(root, "DocumentCurrencyCode", d.invoice.currency)
        self.supplier()
        self.customer()
        if d.invoice.delivery_date is not None:
            delivery = self.cac(root, "Delivery")
            self.cbc(delivery, "ActualDeliveryDate", d.invoice.delivery_date.isoformat())
        self.payment()
        self.taxes()
        self.totals()
        for i, line in enumerate(d.lines, start=1):
            self.line(i, line)
        return _xml(root)

    def supplier(self) -> None:
        s = self.document.supplier
        party = self.cac(self.cac(self.root, "AccountingSupplierParty"), "Party")
        if s.dic:
            self.cbc(party, "EndpointID", s.dic, schemeID=_SK_DIC)
        if s.name:
            self.cbc(self.cac(party, "PartyName"), "Name", s.name)
        if s.address:
            self.address(party, split_address(s.address))
        if s.ic_dph:
            scheme = self.cac(party, "PartyTaxScheme")
            self.cbc(scheme, "CompanyID", s.ic_dph)
            self.cbc(self.cac(scheme, "TaxScheme"), "ID", "VAT")
        legal = self.cac(party, "PartyLegalEntity")
        self.cbc(legal, "RegistrationName", s.name or "")
        if s.ico:
            self.cbc(legal, "CompanyID", s.ico)

    def address(self, party: etree._Element, address: Address) -> None:
        postal = self.cac(party, "PostalAddress")
        self.cbc(postal, "StreetName", address.street)
        if address.city:
            self.cbc(postal, "CityName", address.city)
        if address.zone:
            self.cbc(postal, "PostalZone", address.zone)
        self.cbc(self.cac(postal, "Country"), "IdentificationCode", "SK")

    def customer(self) -> None:
        c = self.document.customer
        party = self.cac(self.cac(self.root, "AccountingCustomerParty"), "Party")
        if c.name:
            self.cbc(self.cac(party, "PartyName"), "Name", c.name)
        postal = self.cac(party, "PostalAddress")
        self.cbc(self.cac(postal, "Country"), "IdentificationCode", "SK")
        legal = self.cac(party, "PartyLegalEntity")
        self.cbc(legal, "RegistrationName", c.name or "")
        if c.ico:
            self.cbc(legal, "CompanyID", c.ico)

    def payment(self) -> None:
        d = self.document
        due_on_means = self.credit and d.invoice.due_date is not None
        if not (d.supplier.iban or d.invoice.variable_symbol or due_on_means):
            return
        means = self.cac(self.root, "PaymentMeans")
        self.cbc(means, "PaymentMeansCode", "30")
        if due_on_means:
            assert d.invoice.due_date is not None
            self.cbc(means, "PaymentDueDate", d.invoice.due_date.isoformat())
        if d.invoice.variable_symbol:
            self.cbc(means, "PaymentID", d.invoice.variable_symbol)
        if d.supplier.iban:
            self.cbc(self.cac(means, "PayeeFinancialAccount"), "ID", _compact(d.supplier.iban))

    def taxes(self) -> None:
        d = self.document
        total = self.cac(self.root, "TaxTotal")
        self.amount(total, "TaxAmount", d.totals.vat or Decimal(0))
        for group in tax_groups(d):
            subtotal = self.cac(total, "TaxSubtotal")
            self.amount(subtotal, "TaxableAmount", group.taxable)
            self.amount(subtotal, "TaxAmount", group.tax)
            self.category(subtotal, "TaxCategory", group.category, group.rate)

    def category(
        self, parent: etree._Element, name: str, category: TaxCategory, rate: Decimal
    ) -> None:
        element = self.cac(parent, name)
        self.cbc(element, "ID", category)
        if category != "O":
            self.cbc(element, "Percent", _number(rate))
        if category == "E":
            self.cbc(element, "TaxExemptionReason", "Oslobodené od dane")
        elif category == "O" and name == "TaxCategory":
            self.cbc(element, "TaxExemptionReason", "Nie je predmetom DPH")
        self.cbc(self.cac(element, "TaxScheme"), "ID", "VAT")

    def totals(self) -> None:
        d = self.document
        if d.totals.gross is None:
            raise ValueError(f"{d.id} has no total")
        payer = vat_payer(d)
        lines = sum((_taxable(d, line) for line in d.lines), Decimal(0))
        exclusive = d.totals.net if payer and d.totals.net is not None else d.totals.gross
        total = self.cac(self.root, "LegalMonetaryTotal")
        self.amount(total, "LineExtensionAmount", lines)
        self.amount(total, "TaxExclusiveAmount", exclusive)
        self.amount(total, "TaxInclusiveAmount", d.totals.gross)
        self.amount(total, "PayableAmount", d.totals.gross)

    def line(self, number: int, line: InvoiceLine) -> None:
        d = self.document
        element = self.cac(self.root, "CreditNoteLine" if self.credit else "InvoiceLine")
        self.cbc(element, "ID", str(number))
        if line.quantity is not None:
            self.cbc(
                element,
                "CreditedQuantity" if self.credit else "InvoicedQuantity",
                _number(line.quantity),
                unitCode=code_of(line.unit or "ks"),
            )
        self.amount(element, "LineExtensionAmount", _taxable(d, line))
        item = self.cac(element, "Item")
        self.cbc(item, "Name", line.description)
        category, rate = tax_category(d, line)
        self.category(item, "ClassifiedTaxCategory", category, rate)
        if line.quantity is not None and line.unit_price is not None:
            price = self.cac(element, "Price")
            self.cbc(price, "PriceAmount", _number(line.unit_price), currencyID=d.invoice.currency)


def ubl_invoice(document: InvoiceDocument) -> bytes:
    """The case as a Peppol BIS Billing 3.0 invoice, or credit note, on UBL 2.1."""
    return _Ubl(document).build()


# --- ISDOC ----------------------------------------------------------------------------------


class _Isdoc:
    def __init__(self, document: InvoiceDocument, case_id: str) -> None:
        self.document = document
        self.case_id = case_id
        self.root = etree.Element(
            f"{{{_ISDOC}}}Invoice", {"version": "6.0.2"}, nsmap={None: _ISDOC}
        )

    def el(self, parent: etree._Element, name: str, text: str | None = None) -> etree._Element:
        element = etree.SubElement(parent, f"{{{_ISDOC}}}{name}")
        if text is not None:
            element.text = text
        return element

    def build(self) -> bytes:
        d = self.document
        root = self.root
        self.el(root, "DocumentType", "2" if _credit(d) else "1")
        self.el(root, "ID", d.invoice.number or d.id)
        self.el(root, "UUID", str(uuid.uuid5(uuid.NAMESPACE_URL, f"riso:testdata:{self.case_id}")))
        if d.invoice.issue_date is None:
            raise ValueError(f"{d.id} has no issue date")
        self.el(root, "IssueDate", d.invoice.issue_date.isoformat())
        if d.invoice.delivery_date is not None:
            self.el(root, "TaxPointDate", d.invoice.delivery_date.isoformat())
        self.el(root, "VATApplicable", "true" if vat_payer(d) else "false")
        self.el(root, "ElectronicPossibilityAgreementReference", "")
        if d.free_text:
            self.el(root, "Note", "\n".join(d.free_text))
        self.el(root, "LocalCurrencyCode", d.invoice.currency)
        self.el(root, "CurrRate", "1")
        self.el(root, "RefCurrRate", "1")
        self.supplier()
        self.customer()
        lines = self.el(root, "InvoiceLines")
        for i, line in enumerate(d.lines, start=1):
            self.line(lines, i, line)
        self.taxes()
        self.totals()
        self.payment()
        return _xml(root)

    def party(
        self,
        parent: etree._Element,
        *,
        ico: str | None,
        name: str | None,
        address: Address,
        ic_dph: str | None = None,
        dic: str | None = None,
    ) -> None:
        party = self.el(parent, "Party")
        self.el(self.el(party, "PartyIdentification"), "ID", ico or "")
        self.el(self.el(party, "PartyName"), "Name", name or "")
        postal = self.el(party, "PostalAddress")
        street, number = address.street_and_number()
        self.el(postal, "StreetName", street)
        self.el(postal, "BuildingNumber", number)
        self.el(postal, "CityName", address.city or "")
        self.el(postal, "PostalZone", address.zone or "")
        country = self.el(postal, "Country")
        self.el(country, "IdentificationCode", "SK")
        self.el(country, "Name", "Slovensko")
        for company_id, scheme in ((ic_dph, "VAT"), (dic, "TIN")):
            if company_id:
                tax = self.el(party, "PartyTaxScheme")
                self.el(tax, "CompanyID", company_id)
                self.el(tax, "TaxScheme", scheme)

    def supplier(self) -> None:
        s = self.document.supplier
        self.party(
            self.el(self.root, "AccountingSupplierParty"),
            ico=s.ico,
            name=s.name,
            address=split_address(s.address or ""),
            ic_dph=s.ic_dph,
            dic=s.dic,
        )

    def customer(self) -> None:
        c = self.document.customer
        self.party(
            self.el(self.root, "AccountingCustomerParty"),
            ico=c.ico,
            name=c.name,
            address=Address("", None, "Boldog" if c.name == "Obec Boldog" else None),
        )

    def money(self, parent: etree._Element, name: str, value: Decimal) -> None:
        self.el(parent, name, _money(value))

    def line(self, parent: etree._Element, number: int, line: InvoiceLine) -> None:
        d = self.document
        category, rate = tax_category(d, line)
        taxable = _taxable(d, line)
        tax = line.vat or Decimal(0)
        gross = line.gross if line.gross is not None else taxable + tax
        element = self.el(parent, "InvoiceLine")
        self.el(element, "ID", str(number))
        if line.quantity is not None:
            quantity = self.el(element, "InvoicedQuantity", _number(line.quantity))
            if line.unit:
                quantity.set("unitCode", line.unit)
        self.money(element, "LineExtensionAmount", taxable)
        self.money(element, "LineExtensionAmountTaxInclusive", gross)
        self.money(element, "LineExtensionTaxAmount", tax)
        priced = line.quantity is not None and line.unit_price is not None
        unit_price = line.unit_price if priced and line.unit_price is not None else taxable
        self.el(element, "UnitPrice", _number(unit_price))
        self.el(element, "UnitPriceTaxInclusive", _number(unit_price * (1 + rate / 100)))
        classified = self.el(element, "ClassifiedTaxCategory")
        self.el(classified, "Percent", _number(rate))
        self.el(classified, "VATCalculationMethod", "0")
        self.el(classified, "VATApplicable", "true" if category == "S" else "false")
        self.el(self.el(element, "Item"), "Description", line.description)

    def taxes(self) -> None:
        d = self.document
        total = self.el(self.root, "TaxTotal")
        for group in tax_groups(d):
            subtotal = self.el(total, "TaxSubTotal")
            inclusive = group.taxable + group.tax
            for name, value in (
                ("TaxableAmount", group.taxable),
                ("TaxAmount", group.tax),
                ("TaxInclusiveAmount", inclusive),
                ("AlreadyClaimedTaxableAmount", Decimal(0)),
                ("AlreadyClaimedTaxAmount", Decimal(0)),
                ("AlreadyClaimedTaxInclusiveAmount", Decimal(0)),
                ("DifferenceTaxableAmount", group.taxable),
                ("DifferenceTaxAmount", group.tax),
                ("DifferenceTaxInclusiveAmount", inclusive),
            ):
                self.money(subtotal, name, value)
            category = self.el(subtotal, "TaxCategory")
            self.el(category, "Percent", _number(group.rate))
            self.el(category, "VATApplicable", "true" if group.category == "S" else "false")
        self.money(total, "TaxAmount", d.totals.vat or Decimal(0))

    def totals(self) -> None:
        d = self.document
        if d.totals.gross is None:
            raise ValueError(f"{d.id} has no total")
        payer = vat_payer(d)
        exclusive = d.totals.net if payer and d.totals.net is not None else d.totals.gross
        total = self.el(self.root, "LegalMonetaryTotal")
        for name, value in (
            ("TaxExclusiveAmount", exclusive),
            ("TaxInclusiveAmount", d.totals.gross),
            ("AlreadyClaimedTaxExclusiveAmount", Decimal(0)),
            ("AlreadyClaimedTaxInclusiveAmount", Decimal(0)),
            ("DifferenceTaxExclusiveAmount", exclusive),
            ("DifferenceTaxInclusiveAmount", d.totals.gross),
            ("PaidDepositsAmount", Decimal(0)),
            ("PayableAmount", d.totals.gross),
        ):
            self.money(total, name, value)

    def payment(self) -> None:
        d = self.document
        if d.invoice.due_date is None and not d.supplier.iban and not d.invoice.variable_symbol:
            return
        assert d.totals.gross is not None
        payment = self.el(self.el(self.root, "PaymentMeans"), "Payment")
        self.money(payment, "PaidAmount", d.totals.gross)
        self.el(payment, "PaymentMeansCode", "42")
        details = self.el(payment, "Details")
        due = d.invoice.due_date or d.invoice.issue_date
        assert due is not None
        self.el(details, "PaymentDueDate", due.isoformat())
        iban = _compact(d.supplier.iban or "")
        # A Slovak IBAN: SKkk, the bank's four digits, then the account (prefix and number).
        bank, account = (iban[4:8], iban[8:].lstrip("0")) if iban.startswith("SK") else ("", "")
        self.el(details, "ID", account)
        self.el(details, "BankCode", bank)
        self.el(details, "Name", "")
        self.el(details, "IBAN", iban)
        self.el(details, "BIC", "")
        if d.invoice.variable_symbol:
            self.el(details, "VariableSymbol", d.invoice.variable_symbol)


def isdoc_invoice(document: InvoiceDocument, case_id: str) -> bytes:
    """The case as an ISDOC 6.0.2 invoice (a credit note is document type 2)."""
    return _Isdoc(document, case_id).build()


# --- ISDOC in a PDF -------------------------------------------------------------------------


def blank_pdf() -> bytes:
    """An empty A4 page, for tests that need a PDF around an attachment but not its look."""
    import pypdfium2

    pdf = pypdfium2.PdfDocument.new()
    pdf.new_page(595, 842)
    buffer = io.BytesIO()
    pdf.save(buffer)
    return _fixed_id(buffer.getvalue())


def _fixed_id(pdf: bytes) -> bytes:
    """PDFium gives every saved file a random ID; this one is the content's digest, at the
    same length, so the offsets stay valid."""
    match = _TRAILER_ID.search(pdf)
    if match is None:
        return pdf
    blank = pdf[: match.start()] + pdf[match.end() :]
    digest = hashlib.sha256(blank).hexdigest().upper()
    ids = b"".join(
        b"<" + digest[: len(part)].encode() + b">" for part in (match.group(1), match.group(2))
    )
    return pdf[: match.start()] + b"/ID[" + ids + b"]" + pdf[match.end() :]


def attach(pdf_data: bytes, name: str, data: bytes) -> bytes:
    """The PDF with a file attached (an embedded file, as an ISDOC PDF carries its XML).
    PDFium stamps the attachment with the time and the file with a random ID; both are
    fixed, so the same input gives the same bytes."""
    import pypdfium2

    pdf = pypdfium2.PdfDocument(pdf_data)
    attachment = pdf.new_attachment(name)
    attachment.set_data(data)
    attachment.set_str_value("CreationDate", _FIXED_DATE)
    attachment.set_str_value("ModDate", _FIXED_DATE)
    buffer = io.BytesIO()
    pdf.save(buffer)
    return _fixed_id(buffer.getvalue())


def isdoc_pdf(document: InvoiceDocument, case_id: str, base_pdf: bytes | None = None) -> bytes:
    return attach(
        base_pdf if base_pdf is not None else blank_pdf(),
        _UNSAFE_NAME.sub("-", document.invoice.number or case_id) + ".isdoc",
        isdoc_invoice(document, case_id),
    )


# --- what each format carries ---------------------------------------------------------------


def expected_document(document: InvoiceDocument, family: Family) -> InvoiceDocument:
    """The case's document as an e-invoice of the format reads back (decision 65): no
    handwritten note; the address as `street, PSČ city`; `vat_payer` as the format states it;
    units through UN/ECE codes (UBL); a UBL line carries no VAT and no gross (Peppol has
    neither), a non-payer's lines and totals only their gross, and a line without a quantity
    no unit price. `id`, `ocr_meta` and `intake` are the reader's and are not compared."""
    payer = vat_payer(document)
    lines = []
    for line in document.lines:
        category, _ = tax_category(document, line)
        update: dict[str, object] = {}
        if line.quantity is None:
            update["unit_price"] = None
        if category == "O":
            update |= {
                "net": None,
                "vat": None,
                "vat_rate": None,
                "gross": _taxable(document, line),
            }
        elif family == "ubl":
            update |= {"vat": None, "gross": None}
        elif line.gross is None:
            update["gross"] = _taxable(document, line) + (line.vat or Decimal(0))
        if family == "ubl" and line.quantity is not None:
            update["unit"] = unit_of(code_of(line.unit or "ks"))
        lines.append(line.model_copy(update=update))
    supplier = document.supplier.model_copy(
        update={
            "vat_payer": payer,
            "address": split_address(document.supplier.address).text
            if document.supplier.address
            else None,
        }
    )
    totals = document.totals
    if not payer:
        totals = totals.model_copy(update={"net": None, "vat": None, "vat_rates": []})
    return document.model_copy(
        update={
            "supplier": supplier,
            "handwritten": document.handwritten.model_copy(update={"date": None, "number": None}),
            "totals": totals.model_copy(update={"vat_rates": sorted(totals.vat_rates)}),
            "lines": lines,
        }
    )


# --- the command ----------------------------------------------------------------------------


def case_files(case: DatasetCase, base_pdf: bytes | None = None) -> dict[str, bytes]:
    """One case's three files, by name."""
    document = case.invoice
    return {
        f"{case.id}.ubl.xml": ubl_invoice(document),
        f"{case.id}.isdoc": isdoc_invoice(document, case.id),
        f"{case.id}.isdoc.pdf": isdoc_pdf(document, case.id, base_pdf),
    }


def generate(
    out: Path,
    *,
    seed: int = DEFAULT_SEED,
    only: Sequence[str] | None = None,
    base_pdfs: Callable[[Sequence[DatasetCase]], dict[str, bytes]] | None = None,
    progress: bool = False,
) -> dict[str, dict[str, str]]:
    """Write the e-invoices of the dataset's cases (or of the case IDs in `only`) into `out`,
    replacing what was there, and the manifest. `base_pdfs` gives each case's digital PDF
    (the scan set's rendering, `riso.testdata.scans.digital_pdfs`); without it the ISDOC is
    attached to a blank page."""
    cases = dataset_cases()
    known = {case.id for case in cases}
    unknown = sorted(set(only or ()) - known)
    if unknown:
        raise ValueError(f"no seed or held-out case {', '.join(unknown)}")
    chosen = [case for case in cases if only is None or case.id in only]
    bases = base_pdfs(chosen) if base_pdfs is not None else {}

    out.mkdir(parents=True, exist_ok=True)
    for stale in out.iterdir():
        if stale.is_file() and stale.name.split(".")[0] in known | {"manifest"}:
            stale.unlink()
    digests: dict[str, dict[str, str]] = {}
    for i, case in enumerate(chosen, start=1):
        files = case_files(case, bases.get(case.id))
        for name, data in files.items():
            (out / name).write_bytes(data)
        digests[case.id] = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        if progress:
            print(f"  {i:2d}/{len(chosen)}  {case.id}")
    manifest = {"seed": seed, "cases": digests}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return digests


SAMPLES: tuple[str, ...] = SAMPLE_CASES
"""The committed samples: the scan set's, so each has its scan and digital PDF too."""
