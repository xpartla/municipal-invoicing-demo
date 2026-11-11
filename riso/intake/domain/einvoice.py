"""E-invoice formats (plan §8.4): Peppol BIS Billing 3.0 on UBL 2.1 (an invoice or a credit
note) and ISDOC 6, as a file of its own or attached to a PDF."""

from enum import StrEnum


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
