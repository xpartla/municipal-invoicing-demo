"""Lines of a layout as searchable text: each line's text, its folded form for labels (lower
case, no diacritics, the same length), and which word every character belongs to."""

import unicodedata
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from riso.intake.domain.layout import Box, DocumentLayout, Word


def _fold_char(char: str) -> str:
    folded = "".join(c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c))
    return folded.lower() if len(folded) == 1 else char.lower()


def fold(text: str) -> str:
    """Lower case without diacritics, character for character, so spans carry over."""
    return "".join(_fold_char(c) for c in unicodedata.normalize("NFC", text))


@dataclass(frozen=True, slots=True)
class TextLine:
    page: int
    order: int
    """The line's position in reading order over the whole document."""
    words: tuple[Word, ...]
    text: str
    spans: tuple[tuple[int, int], ...]
    """Each word's start and end in `text`."""
    page_width: int
    page_height: int
    folded: str
    """`text` folded for the labels: lower case, no diacritics, the same length."""

    @classmethod
    def of(
        cls, page: int, order: int, words: Sequence[Word], width: int, height: int
    ) -> "TextLine":
        parts, spans, at = [], [], 0
        for word in words:
            text = unicodedata.normalize("NFC", word.text)
            spans.append((at, at + len(text)))
            parts.append(text)
            at += len(text) + 1
        text = " ".join(parts)
        return cls(page, order, tuple(words), text, tuple(spans), width, height, fold(text))

    @property
    def box(self) -> Box:
        box = Box.around(w.box for w in self.words)
        assert box is not None
        return box

    def words_in(self, start: int, end: int) -> tuple[Word, ...]:
        """The words a span of `text` touches."""
        return tuple(
            word
            for word, (a, b) in zip(self.words, self.spans, strict=True)
            if a < end and b > start
        )

    def box_of(self, start: int, end: int) -> Box | None:
        return Box.around(w.box for w in self.words_in(start, end))

    def confidence_of(self, start: int, end: int) -> float:
        words = self.words_in(start, end)
        return min((w.confidence for w in words), default=0.0)

    def after(self, start: int) -> int:
        """The first word boundary at or after `start`."""
        return start


def text_lines(layout: DocumentLayout) -> list[TextLine]:
    lines: list[TextLine] = []
    for page in layout.pages:
        for line in page.lines():
            lines.append(TextLine.of(page.index, len(lines), line.words, page.width, page.height))
    return lines


def same_row(a: Box, b: Box) -> bool:
    """Whether two boxes sit on one row: they overlap vertically by at least 40% of the
    lower one, or their middles are within half the taller one's height (a label beside a
    value printed larger)."""
    overlap = min(a.y1, b.y1) - max(a.y0, b.y0)
    if overlap >= 0.4 * min(a.height, b.height):
        return True
    return abs(a.centre[1] - b.centre[1]) < 0.5 * max(a.height, b.height)


def iter_rows(lines: Sequence[TextLine]) -> Iterator[list[TextLine]]:
    """Lines of one page grouped into rows, top to bottom (columns side by side)."""
    pending = sorted(lines, key=lambda ln: (ln.page, ln.box.y0, ln.box.x0))
    row: list[TextLine] = []
    for line in pending:
        if row and (line.page != row[0].page or not same_row(row[0].box, line.box)):
            yield sorted(row, key=lambda ln: ln.box.x0)
            row = []
        row.append(line)
    if row:
        yield sorted(row, key=lambda ln: ln.box.x0)
