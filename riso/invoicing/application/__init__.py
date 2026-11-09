"""Use cases (commands and queries), views (DTOs) and ports of the invoicing context. A use case
checks its permission first, runs in one unit of work, and returns views, never entities or ORM
objects."""

from riso.invoicing.application.booking import (
    BookInvoice,
    book_invoice,
    discard_invoice,
    mark_paid,
    mark_paid_many,
    preview_booking,
    unbook_invoice,
)
from riso.invoicing.application.coding import (
    ReferenceData,
    SupplierState,
    booking_year,
    check_invoice,
    code_document,
    code_stored,
    line_for,
    recode_invoice,
)
from riso.invoicing.application.numbering import (
    SeriesView,
    UsedNumberView,
    list_series,
    preview_number,
    set_last_used,
    take_number,
)
from riso.invoicing.application.state import (
    PastPrecedent,
    add_past_bookings,
    copy_memory,
    counters,
    restore_state,
    supplier_memory,
)
from riso.invoicing.application.uow import InvoicingUnitOfWork, SeriesPatterns
from riso.invoicing.application.views import (
    BookingResult,
    BookingView,
    HistoryEntryView,
    InvoiceView,
    ItemResult,
    PlacementView,
    ShiftView,
)

__all__ = [
    "BookInvoice",
    "BookingResult",
    "BookingView",
    "HistoryEntryView",
    "InvoiceView",
    "InvoicingUnitOfWork",
    "ItemResult",
    "PlacementView",
    "ShiftView",
    "book_invoice",
    "check_invoice",
    "code_stored",
    "discard_invoice",
    "line_for",
    "mark_paid",
    "mark_paid_many",
    "preview_booking",
    "recode_invoice",
    "unbook_invoice",
    "PastPrecedent",
    "ReferenceData",
    "SeriesPatterns",
    "SeriesView",
    "SupplierState",
    "UsedNumberView",
    "add_past_bookings",
    "booking_year",
    "code_document",
    "copy_memory",
    "counters",
    "list_series",
    "preview_number",
    "restore_state",
    "set_last_used",
    "supplier_memory",
    "take_number",
]
