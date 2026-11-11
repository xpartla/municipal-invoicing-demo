"""What the UBL and ISDOC readers share: reading values out of elements, and the values'
printed forms (an IBAN in groups of four, the address as `street, PSČ city`, the VS)."""

import datetime as dt
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from lxml import etree

from riso.contracts import InvoiceDocument

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ICO = re.compile(r"\d{6,8}")
_DIC = re.compile(r"\d{10}")
_VS = re.compile(r"\d{1,10}")
_VS_IN_TEXT = re.compile(r"VS\s*[:.]?\s*(\d{1,10})(?!\d)", re.IGNORECASE)


class Node:
    """An element with the namespaces its paths use; every read is lenient: a missing or
    malformed value is None (the XSD check reports what is malformed)."""

    __slots__ = ("element", "ns")

    def __init__(self, element: etree._Element, ns: Mapping[str, str]) -> None:
        self.element = element
        self.ns = ns

    def find(self, path: str) -> "Node | None":
        found = self.element.find(path, self.ns)
        return Node(found, self.ns) if found is not None else None

    def findall(self, path: str) -> list["Node"]:
        return [Node(e, self.ns) for e in self.element.findall(path, self.ns)]

    def text(self, path: str | None = None) -> str | None:
        element = self.element if path is None else self.element.find(path, self.ns)
        if element is None or element.text is None:
            return None
        value = " ".join(element.text.split())
        return value or None

    def lines(self, path: str) -> list[str]:
        """The texts of every element at the path, split into their lines."""
        found: list[str] = []
        for element in self.element.findall(path, self.ns):
            for line in (element.text or "").splitlines():
                if line.strip():
                    found.append(" ".join(line.split()))
        return found

    def attr(self, name: str) -> str | None:
        value = self.element.get(name)
        return value.strip() if value and value.strip() else None

    def decimal(self, path: str | None = None) -> Decimal | None:
        text = self.text(path)
        if text is None:
            return None
        try:
            value = Decimal(text.replace(" ", ""))
        except InvalidOperation:
            return None
        return value if value.is_finite() else None

    def date(self, path: str) -> dt.date | None:
        text = self.text(path)
        if text is None or not _DATE.match(text):
            return None
        try:
            return dt.date.fromisoformat(text[:10])
        except ValueError:
            return None


def compact(text: str) -> str:
    return "".join(text.split()).upper()


def printed_iban(text: str | None) -> str | None:
    """An IBAN as invoices print it: in groups of four."""
    if not text:
        return None
    value = compact(text)
    return " ".join(value[i : i + 4] for i in range(0, len(value), 4))


def ico_of(*texts: str | None) -> str | None:
    """The first of the texts that is an IČO (six to eight digits)."""
    for text in texts:
        if text and _ICO.fullmatch(compact(text)):
            return compact(text)
    return None


def dic_of(*texts: str | None) -> str | None:
    """The first of the texts that is a Slovak DIČ (ten digits), or one read off an IČ DPH
    (`SK` and the DIČ)."""
    for text in texts:
        if not text:
            continue
        value = compact(text).removeprefix("SK")
        if _DIC.fullmatch(value):
            return value
    return None


def variable_symbol(text: str | None) -> str | None:
    """The VS: a payment reference of at most ten digits, or `VS…` inside a longer one."""
    if not text:
        return None
    value = compact(text)
    if _VS.fullmatch(value):
        return value
    match = _VS_IN_TEXT.search(text)
    return match.group(1) if match else None


def address(street: str | None, zone: str | None, city: str | None) -> str | None:
    """`Čulenova 6, 816 47 Bratislava`; None when there is nothing."""
    place = " ".join(p for p in (zone, city) if p)
    joined = ", ".join(p for p in (street, place) if p)
    return joined or None


def confidences(document: InvoiceDocument) -> dict[str, float]:
    """1.0 for every field the e-invoice gave (plan §8.4): it is what the supplier sent, not
    a reading of it. Fields failing a business check are marked by the check's warning."""
    found: dict[str, float] = {}
    for part in ("supplier", "customer", "invoice", "totals"):
        for name, value in getattr(document, part).model_dump().items():
            if value not in (None, []):
                found[f"{part}.{name}"] = 1.0
    for i, line in enumerate(document.lines):
        for name, value in line.model_dump().items():
            if value is not None:
                found[f"lines[{i}].{name}"] = 1.0
    return found
