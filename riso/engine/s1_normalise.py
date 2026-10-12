"""S1, invoice normalisation: ISO dates, decimal amounts, derived gross, IČO normalisation,
diacritics-free tokens of all text, the VAT flag, the handwritten date and number, and
credit-note detection."""

from riso.contracts import InvoiceDocument
from riso.engine.models import NormalisedInvoice


def normalise(document: InvoiceDocument) -> NormalisedInvoice:
    raise NotImplementedError("S1, invoice normalisation, is built in M1")
