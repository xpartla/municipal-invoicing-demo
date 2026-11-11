"""Reading values out of OCR text (plan §8.2 step 4): amounts with a decimal comma, dates
with dots, IČO, DIČ, IČ DPH, IBAN, the variable symbol and the invoice number. Each finder
returns the matches in a text with where they are, so the caller can tell which word gave
them. OCR's usual confusions inside numbers (O for 0, l or I for 1, S for 5, B for 8) are
undone only where the surrounding characters are digits."""

import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from riso.shared.values import iban_is_valid, ico_is_valid


@dataclass(frozen=True, slots=True)
class Found:
    value: str
    start: int
    end: int
    """The match's span in the text searched."""


_CONFUSED = str.maketrans(
    {"O": "0", "o": "0", "D": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8", "Z": "2"}
)
_DIGITISH = re.compile(r"(?<![A-Za-z])[0-9OoDlI|SBZ]*\d[0-9OoDlI|SBZ]*(?![A-Za-z])")


def undo_confusions(text: str) -> str:
    """`35B23551` → `35823551` where a run is mostly digits; words are left alone."""

    def fix(match: re.Match[str]) -> str:
        run = match.group(0)
        digits = sum(c.isdigit() for c in run)
        return run.translate(_CONFUSED) if digits >= max(2, len(run) - 2) else run

    return _DIGITISH.sub(fix, text)


_AMOUNT = re.compile(
    r"(?<![\d,.])(-|−)?\s?(\d{1,3}(?:[  .]\d{3})+|\d+)(?:,(\d{2}))(?![\d])"
    r"|(?<![\d,.])(-|−)?(\d+)\.(\d{2})(?![\d.,])"
)


def amounts(text: str) -> list[tuple[Decimal, Found]]:
    """Amounts as Slovak invoices print them: `1 234,56`, `1.234,56`, `-52,27`, `93,71 €`;
    also `1234.56` with a decimal point and exactly two decimals."""
    found = []
    for match in _AMOUNT.finditer(text):
        if match.group(2) is not None:
            sign, whole, cents = match.group(1), match.group(2), match.group(3)
        else:
            sign, whole, cents = match.group(4), match.group(5), match.group(6)
        digits = re.sub(r"[  .]", "", whole)
        try:
            value = Decimal(f"{digits}.{cents}")
        except InvalidOperation:
            continue
        if sign:
            value = -value
        found.append((value, Found(str(value), match.start(), match.end())))
    return found


_DATE = re.compile(r"(?<![\d,])(\d{1,2})\s?[.,]\s?(\d{1,2})\s?\.\s?(\d{4}|\d{2})(?![\d,])")


def dates(text: str, *, earliest: int = 2000, latest: int = 2100) -> list[tuple[dt.date, Found]]:
    """`1.7.2026`, `01.07.2026`, `1. 7. 2026`, `1.7.26` as dates; impossible ones are skipped."""
    found = []
    for match in _DATE.finditer(text):
        day, month, year = (int(g) for g in match.groups())
        if year < 100:
            year += 2000
        if not earliest <= year <= latest:
            continue
        try:
            value = dt.date(year, month, day)
        except ValueError:
            continue
        found.append((value, Found(value.isoformat(), match.start(), match.end())))
    return found


_ICO = re.compile(r"(?<!\d)(\d{2}\s?\d{3}\s?\d{3}|\d{6,8})(?!\d)")


def icos(text: str) -> list[tuple[str, Found]]:
    """Eight-digit numbers, also printed `35 823 551`; six and seven digits get their
    leading zeros back, as old IČOs are written."""
    found = []
    for match in _ICO.finditer(undo_confusions(text)):
        digits = re.sub(r"\s", "", match.group(1))
        if len(digits) < 8:
            digits = digits.zfill(8)
        found.append((digits, Found(digits, match.start(), match.end())))
    return found


def ico_valid(ico: str) -> bool:
    return ico_is_valid(ico)


_DIC = re.compile(r"(?<![\dA-Z])(\d{10})(?!\d)")
_IC_DPH = re.compile(r"(?<![A-Z])(SK)\s?(\d{10})(?!\d)")


def dics(text: str) -> list[tuple[str, Found]]:
    return [
        (m.group(1), Found(m.group(1), m.start(), m.end()))
        for m in _DIC.finditer(undo_confusions(text))
    ]


def ic_dphs(text: str) -> list[tuple[str, Found]]:
    found = []
    for match in _IC_DPH.finditer(undo_confusions(text.upper()).replace("5K", "SK")):
        value = f"SK{match.group(2)}"
        found.append((value, Found(value, match.start(), match.end())))
    return found


# The check digits may be misread as letters ("SKO2"), as the rest may.
_CHECK = "[0-9ODISBZ]{2}"
_IBAN = re.compile(rf"(?<![A-Z0-9])([A-Z]{{2}}\s?{_CHECK}(?:\s?[A-Z0-9]){{10,30}})")
_IBAN_AT_END = re.compile(rf"(?<![A-Z0-9])([A-Z]{{2}}\s?{_CHECK}(?:\s?[A-Z0-9]){{0,30}})\s*$")
IBAN_LENGTHS = {"SK": 24, "CZ": 24, "AT": 20, "HU": 28, "PL": 28, "DE": 22}


def ibans(text: str) -> list[tuple[tuple[str, bool], Found]]:
    """IBANs, grouped or not: (compact IBAN, whether it passes mod-97, where). For a country
    whose length is known the match is cut to it; the longest valid reading wins. Check
    digits read as letters are taken only when the IBAN then passes mod-97."""
    found = []
    upper = text.upper()
    for match in _IBAN.finditer(upper):
        raw = match.group(1)
        compact = re.sub(r"\s", "", raw)
        country = compact[:2]
        length = IBAN_LENGTHS.get(country)
        if length is not None:
            if len(compact) < length:
                continue
            compact = compact[:length]
        fixed = compact[:2] + undo_confusions(compact[2:])
        valid = iban_is_valid(fixed)
        if not valid and not compact[2:4].isdigit():
            continue
        found.append(
            ((fixed if valid else compact, valid), Found(compact, match.start(), match.end()))
        )
    return found


def ends_in_cut_iban(text: str) -> bool:
    """Whether the text ends in the start of an IBAN shorter than its country's length: an
    IBAN that a narrow box wraps onto the next line."""
    match = _IBAN_AT_END.search(text.upper())
    if match is None:
        return False
    compact = re.sub(r"\s", "", match.group(1))
    length = IBAN_LENGTHS.get(compact[:2])
    return length is not None and len(compact) < length


_DIGITS = re.compile(r"(?<![\dA-Za-z])(\d{1,10})(?![\d])")


def digit_runs(text: str) -> list[tuple[str, Found]]:
    """Runs of up to ten digits: a variable symbol."""
    return [
        (m.group(1), Found(m.group(1), m.start(), m.end()))
        for m in _DIGITS.finditer(undo_confusions(text))
    ]


_DOCUMENT_NUMBER = re.compile(
    r"(?<![\w/-])([A-Z0-9][A-Z0-9/_.-]*\d[A-Z0-9/_.-]*)(?![\w/-])", re.IGNORECASE
)


def document_numbers(text: str) -> list[tuple[str, Found]]:
    """An invoice's number: a token with at least one digit (`2026/0012`, `FV-2026-118`)."""
    found = []
    for match in _DOCUMENT_NUMBER.finditer(text):
        value = match.group(1).rstrip(".,")
        found.append((value, Found(value, match.start(), match.start() + len(value))))
    return found
