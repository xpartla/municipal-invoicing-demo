"""Reading ISDOC 6 (plan §8.4): an invoice (document type 1) or a credit note (2, and 6 for
an advance's credit note) to an `InvoiceDocument`, on its own or attached to a PDF.

Where each field is (ISDOC 6.0.2 and its XSD's notes; logged in P2-M6-T01):

- the supplier's name: `PartyName/Name`; IČO: `PartyIdentification/ID`;
- IČ DPH: `PartyTaxScheme` under `VAT`; the Slovak DIČ under `TIN`, else off the IČ DPH;
- IBAN and VS: `PaymentMeans/Payment/Details/IBAN` and `VariableSymbol`; the due date:
  `Details/PaymentDueDate`;
- the date of supply: `TaxPointDate` (DUZP);
- totals from `LegalMonetaryTotal` and `TaxTotal`; whether VAT applies from `VATApplicable`.

ISDOC lines carry net, VAT and gross, so all three are read. A document to which VAT does
not apply (a supplier who is not a payer) gets its amounts as gross only, as its paper invoice
prints them. A credit note is written in positive amounts (ISDOC 5.2.1 on) and read negative,
as the dataset prints it.
"""

from decimal import Decimal

from lxml import etree

from riso.contracts import (
    Handwritten,
    Intake,
    InvoiceCustomer,
    InvoiceDocument,
    InvoiceHeader,
    InvoiceLine,
    InvoiceSupplier,
    OcrMeta,
    Totals,
)
from riso.intake.domain.einvoice import ISDOC_NS, EInvoiceFormat, EInvoiceReading, TaxLine
from riso.intake.domain.units import unit_of
from riso.intake.infrastructure.xml.common import (
    Node,
    address,
    compact,
    confidences,
    dic_of,
    ico_of,
    printed_iban,
    variable_symbol,
)

NS = {"i": ISDOC_NS}
CREDIT_NOTE_TYPES = frozenset({"2", "6"})


def _signed(value: Decimal | None, sign: int) -> Decimal | None:
    return None if value is None else value * sign


def _false(text: str | None) -> bool:
    return (text or "").strip().lower() == "false"


def _address(postal: Node | None) -> str | None:
    if postal is None:
        return None
    street = " ".join(
        p for p in (postal.text("i:StreetName"), postal.text("i:BuildingNumber")) if p
    )
    return address(street or None, postal.text("i:PostalZone"), postal.text("i:CityName"))


def _tax_ids(party: Node) -> tuple[str | None, str | None]:
    """The IČ DPH (`VAT`) and the Slovak DIČ (`TIN`, else read off the IČ DPH)."""
    ids: dict[str, str] = {}
    for scheme in party.findall("i:PartyTaxScheme"):
        name, company = (scheme.text("i:TaxScheme") or "").upper(), scheme.text("i:CompanyID")
        if company and name not in ids:
            ids[name] = compact(company)
    ic_dph = ids.get("VAT")
    return ic_dph, dic_of(ids.get("TIN"), ic_dph)


def read_isdoc(root: etree._Element, fmt: EInvoiceFormat) -> EInvoiceReading:
    doc = Node(root, NS)
    credit = doc.text("i:DocumentType") in CREDIT_NOTE_TYPES
    sign = -1 if credit else 1
    outside_vat = _false(doc.text("i:VATApplicable"))

    blank = Node(etree.Element("x"), NS)
    party = doc.find("i:AccountingSupplierParty/i:Party") or blank
    ic_dph, dic = _tax_ids(party)
    payments = doc.findall("i:PaymentMeans/i:Payment")
    details = [d for p in payments if (d := p.find("i:Details")) is not None]
    supplier = InvoiceSupplier(
        name=party.text("i:PartyName/i:Name"),
        ico=ico_of(party.text("i:PartyIdentification/i:ID")),
        dic=dic,
        ic_dph=ic_dph,
        iban=printed_iban(next((iban for d in details if (iban := d.text("i:IBAN"))), None)),
        address=_address(party.find("i:PostalAddress")),
        vat_payer=True if ic_dph else False if outside_vat else None,
    )
    buyer = doc.find("i:AccountingCustomerParty/i:Party") or blank
    customer = InvoiceCustomer(
        name=buyer.text("i:PartyName/i:Name"), ico=ico_of(buyer.text("i:PartyIdentification/i:ID"))
    )
    header = InvoiceHeader(
        number=doc.text("i:ID"),
        issue_date=doc.date("i:IssueDate"),
        delivery_date=doc.date("i:TaxPointDate"),
        due_date=next((due for d in details if (due := d.date("i:PaymentDueDate"))), None),
        variable_symbol=next(
            (vs for d in details if (vs := variable_symbol(d.text("i:VariableSymbol")))), None
        ),
        currency=doc.text("i:LocalCurrencyCode") or "EUR",
        document_type="credit_note" if credit else "invoice",
    )

    tax_total = doc.find("i:TaxTotal") or blank
    taxes = []
    for subtotal in tax_total.findall("i:TaxSubTotal"):
        rate = subtotal.decimal("i:TaxCategory/i:Percent")
        applies = not _false(subtotal.text("i:TaxCategory/i:VATApplicable"))
        taxes.append(
            TaxLine(
                category="O" if outside_vat else "S" if applies and rate else "E",
                rate=rate,
                taxable=_signed(subtotal.decimal("i:TaxableAmount"), sign),
                tax=_signed(subtotal.decimal("i:TaxAmount"), sign),
            )
        )
    monetary = doc.find("i:LegalMonetaryTotal") or blank
    totals = Totals(
        net=None if outside_vat else _signed(monetary.decimal("i:TaxExclusiveAmount"), sign),
        vat=None if outside_vat else _signed(tax_total.decimal("i:TaxAmount"), sign),
        gross=_signed(monetary.decimal("i:TaxInclusiveAmount"), sign),
        vat_rates=sorted({t.rate for t in taxes if t.category == "S" and t.rate}),
    )

    lines = [_line(n, sign, outside_vat) for n in doc.findall("i:InvoiceLines/i:InvoiceLine")]
    document = InvoiceDocument(
        id="einvoice",
        supplier=supplier,
        customer=customer,
        invoice=header,
        handwritten=Handwritten(),
        totals=totals,
        lines=lines,
        free_text=doc.lines("i:Note"),
        ocr_meta=OcrMeta(),
        intake=Intake(channel="einvoice", format="isdoc"),
    )
    document = document.model_copy(update={"ocr_meta": OcrMeta(confidence=confidences(document))})
    return EInvoiceReading(
        format=fmt,
        version=doc.attr("version") or "6",
        profile=None,
        document=document,
        customer_address=_address(buyer.find("i:PostalAddress")),
        taxes=tuple(taxes),
        payable=_signed(monetary.decimal("i:PayableAmount"), sign),
    )


def _line(node: Node, sign: int, outside_vat: bool) -> InvoiceLine:
    quantity_node = node.find("i:InvoicedQuantity")
    quantity = quantity_node.decimal() if quantity_node is not None else None
    unit = quantity_node.attr("unitCode") if quantity_node is not None else None
    net = _signed(node.decimal("i:LineExtensionAmount"), sign)
    gross = _signed(node.decimal("i:LineExtensionAmountTaxInclusive"), sign)
    vat = _signed(node.decimal("i:LineExtensionTaxAmount"), sign)
    applies = not _false(node.text("i:ClassifiedTaxCategory/i:VATApplicable"))
    return InvoiceLine(
        description=node.text("i:Item/i:Description") or node.text("i:Note") or "",
        quantity=_signed(quantity, sign),
        unit=unit_of(unit) if quantity is not None and unit else None,
        unit_price=node.decimal("i:UnitPrice") if quantity is not None else None,
        net=None if outside_vat else net,
        vat_rate=node.decimal("i:ClassifiedTaxCategory/i:Percent")
        if applies and not outside_vat
        else None,
        vat=None if outside_vat else vat,
        gross=gross if gross is not None else net,
    )
