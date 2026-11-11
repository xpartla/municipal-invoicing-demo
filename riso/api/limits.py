"""How large a request's body may be, per route (plan §12), for `BodySizeLimitMiddleware`.

Uploads take what their routes accept: invoices at most `MAX_FILES` files of `MAX_BYTES`
each, an import one file of `MAX_FILE_BYTES`; the multipart framing and the form's other
fields get a megabyte on top. Every other route takes JSON, of which the largest (an
invoice with its lines, a customer's conventions) stay far below `JSON_LIMIT`.
"""

import re

from riso.exchange.infrastructure.readers import MAX_FILE_BYTES
from riso.intake.application.upload import MAX_FILES
from riso.intake.domain import MAX_BYTES

MIB = 1024 * 1024
JSON_LIMIT = 2 * MIB
FRAMING = MIB
DOCUMENTS_LIMIT = MAX_FILES * MAX_BYTES + FRAMING
IMPORT_LIMIT = MAX_FILE_BYTES + FRAMING

_DOCUMENTS = re.compile(r"^/api/customers/[^/]+/documents$")
_IMPORTS = re.compile(r"^/api/(?:customers/[^/]+|admin)/imports$")


def body_limit(method: str, path: str) -> int:
    """The largest body, in bytes, this request may send."""
    if method == "POST":
        if _DOCUMENTS.match(path):
            return DOCUMENTS_LIMIT
        if _IMPORTS.match(path):
            return IMPORT_LIMIT
    return JSON_LIMIT
