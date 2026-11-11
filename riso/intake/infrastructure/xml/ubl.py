"""Reading Peppol BIS Billing 3.0 / UBL 2.1 (plan §8.4 "The mapping"): an `Invoice` or a
`CreditNote` (or an `Invoice` with a credit note's type code) to an `InvoiceDocument`.

Where each field is looked for, first place first (the Slovak placement is logged in
P2-M6-T01):

- the supplier's name: `PartyLegalEntity/RegistrationName`, `PartyName/Name`;
- IČO: `PartyLegalEntity/CompanyID`, `PartyIdentification/ID` (six to eight digits);
- IČ DPH: `PartyTaxScheme/CompanyID` under the `VAT` scheme;
- DIČ: the `EndpointID` with scheme 0245, a `PartyTaxScheme` under another scheme, the IČ DPH;
- IBAN: `PaymentMeans/PayeeFinancialAccount/ID`; VS: `PaymentMeans/PaymentID`;
- the date of supply: `Delivery/ActualDeliveryDate`, `TaxPointDate`; the due date: `DueDate`,
  `PaymentMeans/PaymentDueDate`;
- totals from `LegalMonetaryTotal` and `TaxTotal`; the rates from its subtotals.

Peppol lines carry no VAT and no gross (decision 65): the engine derives them from the net
and the rate. A supplier not subject to VAT (every category `O`) gets its amounts as gross,
as its paper invoice prints them, and no net or VAT. A credit note's amounts and quantities
are made negative, as the dataset prints them.
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
from riso.intake.domain.einvoice import (
    CAC_NS,
    CBC_NS,
    CREDIT_NOTE_CODES,
    SK_DIC_SCHEME,
    EInvoiceFormat,
    EInvoiceReading,
    TaxLine,
)
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

NS = {"cac": CAC_NS, "cbc": CBC_NS}
_NO_RATE = frozenset({"E", "O", "AE", "K", "G"})
"""Categories whose lines have no VAT rate of their own (exempt, outside VAT, reverse
charge, intra-community, export)."""


def _signed(value: Decimal | None, sign: int) -> Decimal | None:
    return None if value is None else value * sign


def _address(postal: Node | None) -> str | None:
    if postal is None:
        return None
    street = ", ".join(
        p
        for p in (
            postal.text("cbc:StreetName"),
            postal.text("cbc:AdditionalStreetName"),
            postal.text("cac:AddressLine/cbc:Line"),
        )
        if p
    )
    return address(street or None, postal.text("cbc:PostalZone"), postal.text("cbc:CityName"))


def _party_name(party: Node) -> str | None:
    return party.text("cac:PartyLegalEntity/cbc:RegistrationName") or party.text(
        "cac:PartyName/cbc:Name"
    )


def _party_ico(party: Node) -> str | None:
    return ico_of(
        party.text("cac:PartyLegalEntity/cbc:CompanyID"),
        *(p.text() for p in party.findall("cac:PartyIdentification/cbc:ID")),
    )


def _tax_ids(party: Node) -> tuple[str | None, str | None]:
    """The IČ DPH and the DIČ."""
    ic_dph = None
    other: list[str | None] = []
    for scheme in party.findall("cac:PartyTaxScheme"):
        company = scheme.text("cbc:CompanyID")
        if (scheme.text("cac:TaxScheme/cbc:ID") or "").upper() == "VAT":
            ic_dph = ic_dph or (compact(company) if company else None)
        else:
            other.append(company)
    endpoint = party.find("cbc:EndpointID")
    from_endpoint = (
        endpoint.text()
        if endpoint is not None and endpoint.attr("schemeID") == SK_DIC_SCHEME
        else None
    )
    return ic_dph, dic_of(from_endpoint, *other, ic_dph)


def read_ubl(root: etree._Element, fmt: EInvoiceFormat) -> EInvoiceReading:
    doc = Node(root, NS)
    credit = fmt is EInvoiceFormat.UBL_CREDIT_NOTE or (
        doc.text("cbc:InvoiceTypeCode") in CREDIT_NOTE_CODES
    )
    sign = -1 if credit else 1

    tax_total = next(
        (t for t in doc.findall("cac:TaxTotal") if t.find("cac:TaxSubtotal") is not None),
        doc.find("cac:TaxTotal"),
    )
    taxes = [
        TaxLine(
            category=(s.text("cac:TaxCategory/cbc:ID") or "").upper(),
            rate=s.decimal("cac:TaxCategory/cbc:Percent"),
            taxable=_signed(s.decimal("cbc:TaxableAmount"), sign),
            tax=_signed(s.decimal("cbc:TaxAmount"), sign),
        )
        for s in (tax_total.findall("cac:TaxSubtotal") if tax_total is not None else [])
    ]
    line_nodes = doc.findall(
        "cac:CreditNoteLine" if fmt is EInvoiceFormat.UBL_CREDIT_NOTE else "cac:InvoiceLine"
    )
    line_categories = {
        (n.text("cac:Item/cac:ClassifiedTaxCategory/cbc:ID") or "").upper() for n in line_nodes
    } - {""}
    categories = {t.category for t in taxes} - {""} | line_categories
    vat = _signed(tax_total.decimal("cbc:TaxAmount"), sign) if tax_total is not None else None
    outside_vat = bool(categories) and categories <= {"O"} and not vat

    party = doc.find("cac:AccountingSupplierParty/cac:Party") or Node(etree.Element("x"), NS)
    ic_dph, dic = _tax_ids(party)
    means = doc.findall("cac:PaymentMeans")
    supplier = InvoiceSupplier(
        name=_party_name(party),
        ico=_party_ico(party),
        dic=dic,
        ic_dph=ic_dph,
        iban=printed_iban(
            next(
                (
                    m.text("cac:PayeeFinancialAccount/cbc:ID")
                    for m in means
                    if m.text("cac:PayeeFinancialAccount/cbc:ID")
                ),
                None,
            )
        ),
        address=_address(party.find("cac:PostalAddress")),
        vat_payer=True if ic_dph else False if outside_vat else None,
    )
    buyer = doc.find("cac:AccountingCustomerParty/cac:Party") or Node(etree.Element("x"), NS)
    customer = InvoiceCustomer(name=_party_name(buyer), ico=_party_ico(buyer))

    header = InvoiceHeader(
        number=doc.text("cbc:ID"),
        issue_date=doc.date("cbc:IssueDate"),
        delivery_date=doc.date("cac:Delivery/cbc:ActualDeliveryDate")
        or doc.date("cbc:TaxPointDate"),
        due_date=doc.date("cbc:DueDate")
        or next((d for m in means if (d := m.date("cbc:PaymentDueDate"))), None),
        variable_symbol=next(
            (
                vs
                for m in means
                for p in m.findall("cbc:PaymentID")
                if (vs := variable_symbol(p.text()))
            ),
            None,
        ),
        currency=doc.text("cbc:DocumentCurrencyCode") or "EUR",
        document_type="credit_note" if credit else "invoice",
    )

    monetary = doc.find("cac:LegalMonetaryTotal") or Node(etree.Element("x"), NS)
    gross = monetary.decimal("cbc:TaxInclusiveAmount")
    if gross is None:
        gross = monetary.decimal("cbc:PayableAmount")
    totals = Totals(
        net=None if outside_vat else _signed(monetary.decimal("cbc:TaxExclusiveAmount"), sign),
        vat=None if outside_vat else vat,
        gross=_signed(gross, sign),
        vat_rates=sorted({t.rate for t in taxes if t.rate is not None and t.rate > 0}),
    )

    lines = [_line(n, sign, outside_vat) for n in line_nodes]
    document = InvoiceDocument(
        id="einvoice",
        supplier=supplier,
        customer=customer,
        invoice=header,
        handwritten=Handwritten(),
        totals=totals,
        lines=lines,
        free_text=doc.lines("cbc:Note"),
        ocr_meta=OcrMeta(),
        intake=Intake(channel="einvoice", format="ubl"),
    )
    document = document.model_copy(update={"ocr_meta": OcrMeta(confidence=confidences(document))})
    return EInvoiceReading(
        format=fmt,
        version="2.1",
        profile=doc.text("cbc:CustomizationID"),
        document=document,
        customer_address=_address(buyer.find("cac:PostalAddress")),
        taxes=tuple(taxes),
        payable=_signed(monetary.decimal("cbc:PayableAmount"), sign),
    )


def _line(node: Node, sign: int, outside_vat: bool) -> InvoiceLine:
    quantity_node = node.find("cbc:InvoicedQuantity") or node.find("cbc:CreditedQuantity")
    quantity = quantity_node.decimal() if quantity_node is not None else None
    category = (node.text("cac:Item/cac:ClassifiedTaxCategory/cbc:ID") or "").upper()
    percent = node.decimal("cac:Item/cac:ClassifiedTaxCategory/cbc:Percent")
    amount = _signed(node.decimal("cbc:LineExtensionAmount"), sign)
    price = node.decimal("cac:Price/cbc:PriceAmount")
    base = node.decimal("cac:Price/cbc:BaseQuantity")
    if price is not None and base is not None and base not in (0, 1):
        price = price / base
    not_subject = category == "O" or (not category and outside_vat)
    unit_code = quantity_node.attr("unitCode") if quantity_node is not None else None
    return InvoiceLine(
        description=node.text("cac:Item/cbc:Name") or node.text("cac:Item/cbc:Description") or "",
        quantity=_signed(quantity, sign),
        unit=unit_of(unit_code) if quantity is not None and unit_code else None,
        unit_price=price if quantity is not None else None,
        net=None if not_subject else amount,
        vat_rate=None if not_subject or category in _NO_RATE else percent,
        gross=amount if not_subject else None,
    )
