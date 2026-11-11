"""E-invoice formats (plan §8.4): Peppol BIS Billing 3.0 on UBL 2.1 (an invoice or a credit
note) and ISDOC 6, as a file of its own or attached to a PDF."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from riso.contracts import InvoiceDocument
from riso.intake.domain.layout import ReadingFailed
from riso.shared.values import iban_is_valid, ico_is_valid


class EInvoiceFormat(StrEnum):
    UBL_INVOICE = "ubl_invoice"
    UBL_CREDIT_NOTE = "ubl_credit_note"
    ISDOC = "isdoc"

    @property
    def family(self) -> str:
        """`ubl` or `isdoc`: what `intake.format` records, with `_pdf` when the XML came
        attached to a PDF."""
        return "isdoc" if self is EInvoiceFormat.ISDOC else "ubl"


UBL_INVOICE_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
UBL_CREDIT_NOTE_NS = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
ISDOC_NS = "http://isdoc.cz/namespace/2013"

ROOTS: dict[tuple[str, str], EInvoiceFormat] = {
    (UBL_INVOICE_NS, "Invoice"): EInvoiceFormat.UBL_INVOICE,
    (UBL_CREDIT_NOTE_NS, "CreditNote"): EInvoiceFormat.UBL_CREDIT_NOTE,
    (ISDOC_NS, "Invoice"): EInvoiceFormat.ISDOC,
}
"""The root element (namespace, local name) of each format."""

PEPPOL_CUSTOMIZATION = "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
PEPPOL_PROFILE = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
SK_DIC_SCHEME = "0245"
"""The Peppol EAS code of the Slovak DIČ, used for the endpoint (participant) ID."""


# --- what a reader makes of a file ----------------------------------------------------------

CREDIT_NOTE_CODES = frozenset({"381", "396", "81", "83", "532"})
"""UNCL 1001 codes of a credit note, for a credit note sent as a UBL `Invoice`."""


@dataclass(frozen=True, slots=True)
class TaxLine:
    """One line of the VAT breakdown: the category (UNCL 5305 for UBL; `S` or `E` for ISDOC),
    the rate, the base and the tax."""

    category: str
    rate: Decimal | None
    taxable: Decimal | None
    tax: Decimal | None


@dataclass(frozen=True, slots=True)
class EInvoiceReading:
    """What a reader made of one e-invoice: the `InvoiceDocument` (every field at
    confidence 1.0, `intake.channel = einvoice`) and what the rendered view shows besides it.
    Amounts of a credit note are negative, as the dataset prints them."""

    format: EInvoiceFormat
    version: str
    """`2.1` for UBL, the `version` attribute for ISDOC."""
    profile: str | None
    """The Peppol customization (UBL); None for ISDOC."""
    document: InvoiceDocument
    customer_address: str | None
    taxes: tuple[TaxLine, ...]
    payable: Decimal | None
    schema_errors: tuple[str, ...] = ()
    attachment: str | None = None
    """The attachment's name when the XML came inside a PDF."""

    @property
    def intake_format(self) -> str:
        """`ubl`, `isdoc`, `ubl_pdf` or `isdoc_pdf`: what `intake.format` records."""
        return self.format.family + ("_pdf" if self.attachment is not None else "")


def require_essentials(document: InvoiceDocument) -> None:
    """An e-invoice without a supplier or a total is not one riso can use: the extraction
    fails (decision 65), and the user enters it by hand."""
    if not (document.supplier.name or document.supplier.ico):
        raise ReadingFailed("einvoice_no_supplier")
    if document.totals.gross is None:
        raise ReadingFailed("einvoice_no_total")


_TOLERANCE = Decimal("0.01")


def check(
    document: InvoiceDocument, *, customer_ico: str | None, schema_errors: Sequence[str] = ()
) -> tuple[str, ...]:
    """The business checks (plan §8.4): check digits, totals, dates, the customer. Each
    failure is a warning whose code the check step explains and marks its fields by; a
    missing optional field is a warning too, never a failure (decision 65)."""
    warnings: list[str] = []
    if schema_errors:
        warnings.append("einvoice_schema")
    supplier, header, totals = document.supplier, document.invoice, document.totals
    if supplier.ico is None:
        warnings.append("missing_supplier_ico")
    elif not ico_is_valid(supplier.ico.zfill(8)):
        warnings.append("supplier_ico_check_digit")
    if (
        supplier.dic
        and supplier.ic_dph
        and supplier.ic_dph.upper().removeprefix("SK") != (supplier.dic)
    ):
        warnings.append("tax_ids_do_not_match")
    if supplier.iban is None:
        warnings.append("missing_iban")
    elif not iban_is_valid("".join(supplier.iban.split()).upper()):
        warnings.append("iban_check_digits")
    if header.variable_symbol is None:
        warnings.append("missing_variable_symbol")
    if header.due_date is None:
        warnings.append("missing_due_date")
    issue, delivery, due = header.issue_date, header.delivery_date, header.due_date
    if issue is not None and (
        (due is not None and due < issue) or (delivery is not None and (delivery - issue).days > 31)
    ):
        warnings.append("dates_out_of_order")
    net, vat, gross = totals.net, totals.vat, totals.gross
    if (
        net is not None
        and vat is not None
        and gross is not None
        and (abs(net + vat - gross) > _TOLERANCE)
    ):
        warnings.append("totals_do_not_add_up")
    base = totals.net if totals.net is not None else totals.gross
    amounts = [line.net if line.net is not None else line.gross for line in document.lines]
    if base is not None and amounts and all(a is not None for a in amounts):
        lines_total = sum((a for a in amounts if a is not None), Decimal(0))
        if abs(lines_total - base) > _TOLERANCE * max(1, len(amounts)):
            warnings.append("lines_do_not_add_up")
    customer = document.customer.ico
    if customer and customer_ico and customer.zfill(8) != customer_ico.zfill(8):
        warnings.append("addressed_to_another_entity")
    return tuple(dict.fromkeys(warnings))
