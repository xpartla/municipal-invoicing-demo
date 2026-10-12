"""InvoiceDocument: one supplier invoice as the OCR step delivers it (plan section 3.1)."""

import datetime as dt
import re
from typing import Literal

from pydantic import Field, field_validator

from riso.contracts.base import Amount, Contract, Slug

_CONFIDENCE_KEY = re.compile(
    r"^(supplier|customer|invoice|handwritten|totals)\.[a-z_]+$|^lines\[\d+\]\.[a-z_]+$"
)


class InvoiceSupplier(Contract):
    name: str | None = None
    ico: str | None = Field(default=None, description="As read; S1 normalises it")
    dic: str | None = None
    ic_dph: str | None = None
    iban: str | None = None
    address: str | None = None
    vat_payer: bool | None = Field(
        default=None, description="Only when printed, e.g. 'nie som platca DPH' or an IČ DPH"
    )


class InvoiceCustomer(Contract):
    name: str | None = None
    ico: str | None = Field(default=None, description="Picks the entity's reference data")


class InvoiceHeader(Contract):
    number: str | None = None
    issue_date: dt.date | None = None
    delivery_date: dt.date | None = None
    due_date: dt.date | None = None
    variable_symbol: str | None = None
    currency: str = "EUR"
    document_type: Literal["invoice", "credit_note"] | None = Field(
        default=None, description="Only when printed"
    )


class Handwritten(Contract):
    """Written by hand on the scan when the invoice arrives; the position varies per scan."""

    date: dt.date | None = Field(default=None, description="The booking date")
    number: str | None = Field(
        default=None, description="Sequence number of the FD document: '144' becomes FD/144/26"
    )


class Totals(Contract):
    net: Amount | None = None
    vat: Amount | None = None
    gross: Amount | None = None
    vat_rates: list[Amount] = Field(default_factory=list)


class InvoiceLine(Contract):
    description: str
    quantity: Amount | None = None
    unit: str | None = None
    unit_price: Amount | None = None
    net: Amount | None = None
    vat_rate: Amount | None = None
    vat: Amount | None = None
    gross: Amount | None = None


class OcrMeta(Contract):
    source_file: str | None = None
    page_count: int | None = None
    synthetic: bool = Field(default=False, description="Generated for the mock dataset")
    confidence: dict[str, float] = Field(
        default_factory=dict,
        description="OCR confidence per field, keyed by path: 'handwritten.date', 'lines[0].gross'",
    )

    @field_validator("confidence")
    @classmethod
    def _known_paths_in_range(cls, value: dict[str, float]) -> dict[str, float]:
        for path, score in value.items():
            if not _CONFIDENCE_KEY.match(path):
                raise ValueError(f"unknown field path {path!r}")
            if not 0 <= score <= 1:
                raise ValueError(f"confidence of {path!r} must be between 0 and 1")
        return value


class InvoiceDocument(Contract):
    id: Slug = Field(description="Stable identifier, e.g. the dataset case id")
    supplier: InvoiceSupplier
    customer: InvoiceCustomer
    invoice: InvoiceHeader
    handwritten: Handwritten
    totals: Totals
    lines: list[InvoiceLine] = Field(default_factory=list)
    free_text: list[str] = Field(
        default_factory=list,
        description="Anything else the OCR captured: contract references, period served",
    )
    ocr_meta: OcrMeta
