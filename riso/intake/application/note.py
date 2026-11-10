"""Reading the handwritten note (plan §8.2 step 3): the locator finds it on the first page,
the reader reads each of its items for digits only, and the domain marks what was read and
the counter's next number as suggestions. Nothing here fills the invoice's fields."""

import datetime as dt
from collections.abc import Collection

from riso.intake.application.ports import DocumentReader, NoteLocator, PageImage
from riso.intake.domain.layout import PageLayout, ReadingFailed
from riso.intake.domain.note import (
    NoteRegion,
    NoteSuggestions,
    date_suggestions,
    number_suggestions,
    read_note,
)


def note_readings(
    page: PageImage,
    layout: PageLayout,
    locator: NoteLocator,
    reader: DocumentReader,
    *,
    region: NoteRegion | None = None,
) -> tuple[NoteSuggestions, list[str]]:
    """The note's region (located unless given), and what the digits pass read in each of
    its items (the whole crop when no item was found). A reading that fails is skipped: the
    crop stays."""
    region = region or locator.locate(page.image, layout)
    readings = []
    for box in region.groups or (region.box,):
        try:
            read = reader.read_digits(page, box)
        except ReadingFailed:
            continue
        text = " ".join(word.text for word in read.words)
        if text:
            readings.append(text)
    empty = NoteSuggestions(page.index, region.box, region.found, (), ())
    return empty, readings


def suggest(
    note: NoteSuggestions,
    readings: list[str],
    *,
    issue_date: dt.date | None,
    today: dt.date,
    budget_year: int,
    next_number: int | None,
    used: Collection[int],
) -> NoteSuggestions:
    dates, numbers = read_note(readings)
    return NoteSuggestions(
        note.page,
        note.box,
        note.found,
        date_suggestions(dates, issue_date, today, budget_year),
        number_suggestions(numbers, next_number, used),
    )
