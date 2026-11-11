"""Validation against the bundled XSDs (plan §8.4): UBL 2.1 Invoice and CreditNote, and
ISDOC 6.0.2. The schemas are compiled once per process, from the package's own files only
(no network, no entities), and validating is serialised, since a compiled lxml schema is not
meant to be shared by threads at once.
"""

import threading
from functools import cache
from pathlib import Path

from lxml import etree

from riso.intake.domain.einvoice import EInvoiceFormat

SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"

_FILES = {
    EInvoiceFormat.UBL_INVOICE: SCHEMAS_DIR / "ubl-2.1" / "maindoc" / "UBL-Invoice-2.1.xsd",
    EInvoiceFormat.UBL_CREDIT_NOTE: SCHEMAS_DIR / "ubl-2.1" / "maindoc" / "UBL-CreditNote-2.1.xsd",
    EInvoiceFormat.ISDOC: SCHEMAS_DIR / "isdoc-6.0.2" / "isdoc-invoice-6.0.2.xsd",
}

MAX_ERRORS = 10
"""Schema errors reported per file; the rest are counted."""

_lock = threading.Lock()


@cache
def schema(fmt: EInvoiceFormat) -> etree.XMLSchema:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    return etree.XMLSchema(etree.parse(str(_FILES[fmt]), parser))


def schema_errors(root: etree._Element, fmt: EInvoiceFormat) -> list[str]:
    """What the format's XSD finds wrong with the document, as `line N: message`; empty
    when it is valid. At most `MAX_ERRORS`, then a count of the others."""
    compiled = schema(fmt)
    with _lock:
        if compiled.validate(root):
            return []
        errors = list(compiled.error_log)
    shown = [f"line {e.line}: {e.message}" for e in errors[:MAX_ERRORS]]
    if len(errors) > MAX_ERRORS:
        shown.append(f"and {len(errors) - MAX_ERRORS} more")
    return shown
