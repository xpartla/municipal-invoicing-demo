"""The handwritten note's suggestions (plan §8.1 conclusion 2, §8.2 step 3): what the digits
pass read, and the counter's next number, each marked plausible or not. They are offered to
the user and never accepted on their own: the extracted `InvoiceDocument` keeps the
handwritten date and number empty until the user confirms them in the check step.

A number is plausible between the counter's next and next + 50, when it is not used yet; a
date between the invoice's issue date and today, in the budget year.
"""

import datetime as dt
import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Literal

from riso.intake.domain.extract.values import dates
from riso.intake.domain.layout import Box

AHEAD = 50
MAX_SUGGESTIONS = 3
"""Readings offered per field, besides the counter's number."""
"""How far past the counter's next number a handwritten number is still plausible."""
_NUMBER = re.compile(r"(?<![\d./])(\d{1,4})(?![\d./])")


@dataclass(frozen=True, slots=True)
class NoteRegion:
    """Where the note is on a page: the crop, and the ink groups in it (each an item: the
    date, the number); no groups when no ink was found and the crop is the top band."""

    box: Box
    groups: tuple[Box, ...]

    @property
    def found(self) -> bool:
        return bool(self.groups)


@dataclass(frozen=True, slots=True)
class Suggestion:
    value: str
    """A number as written (`144`), a date as ISO 8601."""
    source: Literal["ocr", "counter"]
    plausible: bool
    reasons: tuple[str, ...] = ()
    """Why not: `before_issue`, `in_future`, `other_year`, `below_counter`, `far_ahead`,
    `already_used`."""


@dataclass(frozen=True, slots=True)
class NoteSuggestions:
    page: int
    box: Box
    """The note's crop on the page, shown enlarged in the check step."""
    found: bool
    """Whether ink was found; else the box is the page's top band."""
    date: tuple[Suggestion, ...]
    number: tuple[Suggestion, ...]


def read_note(texts: Iterable[str]) -> tuple[list[dt.date], list[str]]:
    """The dates and the numbers in what the digits pass read, in its order: each reading's
    dates, and its stand-alone runs of one to four digits outside them."""
    found_dates: list[dt.date] = []
    found_numbers: list[str] = []
    for text in texts:
        for value, where in dates(text):
            if value not in found_dates:
                found_dates.append(value)
            text = text[: where.start] + " " * (where.end - where.start) + text[where.end :]
        for match in _NUMBER.finditer(text):
            number = str(int(match.group(1)))
            if number not in found_numbers:
                found_numbers.append(number)
    return found_dates, found_numbers


def _plausible_first(suggestions: list[Suggestion]) -> tuple[Suggestion, ...]:
    return tuple(sorted(suggestions, key=lambda s: not s.plausible)[:MAX_SUGGESTIONS])


def number_suggestions(
    readings: Iterable[str], next_number: int | None, used: Collection[int]
) -> tuple[Suggestion, ...]:
    """What the digits pass read, each marked, and the counter's next number; the
    plausible first."""
    suggestions = []
    seen = set()
    for reading in readings:
        value = int(reading)
        seen.add(value)
        reasons = []
        if next_number is not None and value < next_number:
            reasons.append("below_counter")
        if next_number is not None and value > next_number + AHEAD:
            reasons.append("far_ahead")
        if value in used:
            reasons.append("already_used")
        suggestions.append(Suggestion(str(value), "ocr", not reasons, tuple(reasons)))
    ordered = list(_plausible_first(suggestions))
    if next_number is not None and next_number not in seen:
        ordered.append(Suggestion(str(next_number), "counter", next_number not in used))
    return tuple(ordered)


def date_suggestions(
    readings: Iterable[dt.date], issue: dt.date | None, today: dt.date, budget_year: int
) -> tuple[Suggestion, ...]:
    """What the digits pass read, each marked; the plausible first."""
    suggestions = []
    for reading in readings:
        reasons = []
        if issue is not None and reading < issue:
            reasons.append("before_issue")
        if reading > today:
            reasons.append("in_future")
        if reading.year != budget_year:
            reasons.append("other_year")
        suggestions.append(Suggestion(reading.isoformat(), "ocr", not reasons, tuple(reasons)))
    return _plausible_first(suggestions)
