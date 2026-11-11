"""Finding a label's value (plan §8.2 step 4): on the label's line after it, else to its
right on the same row (a value in the next cell), else below it in its column (a value under
its heading). Each candidate carries the words it was read from."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from riso.intake.domain.extract.labels import LABELS, Label
from riso.intake.domain.extract.text import TextLine, same_row
from riso.intake.domain.extract.values import Found
from riso.intake.domain.layout import Box

Route = Literal["line", "row", "below", "free"]
type Parser[T] = Callable[[str], list[tuple[T, Found]]]

ROUTE_WEIGHT: dict[Route, float] = {"line": 1.0, "row": 0.95, "below": 0.9, "free": 0.6}


@dataclass(frozen=True, slots=True)
class Hit:
    label: Label
    line: TextLine
    start: int
    end: int

    @property
    def box(self) -> Box:
        box = self.line.box_of(self.start, self.end)
        return box if box is not None else self.line.box


@dataclass(frozen=True, slots=True)
class Candidate[T]:
    value: T
    line: TextLine
    start: int
    end: int
    route: Route
    label: Label | None

    @property
    def box(self) -> Box:
        return self.line.box_of(self.start, self.end) or self.line.box

    @property
    def ocr_confidence(self) -> float:
        return self.line.confidence_of(self.start, self.end)

    @property
    def page(self) -> int:
        return self.line.page

    def anchored(self) -> float:
        """How much the way it was found adds up: the route, and a weak label less."""
        weight = ROUTE_WEIGHT[self.route]
        if self.label is not None and self.label.strength == "weak":
            weight *= 0.85
        return weight


def hits(lines: Sequence[TextLine], field: str) -> list[Hit]:
    found = []
    for line in lines:
        for label in LABELS:
            if label.field != field:
                continue
            for match in label.pattern.finditer(line.folded):
                found.append(Hit(label, line, match.start(), match.end()))
    return found


def _first[T](line: TextLine, offset: int, parse: Parser[T]) -> tuple[T, int, int] | None:
    for value, where in parse(line.text[offset:]):
        return value, offset + where.start, offset + where.end
    return None


def values_for[T](
    hit: Hit, lines: Sequence[TextLine], parse: Parser[T], *, below: int = 3
) -> list[Candidate[T]]:
    """The candidates for one label, the likeliest first: the rest of its line, the cells
    to its right on its row, the lines under it (up to `below` of them)."""
    found: list[Candidate[T]] = []
    on_line = _first(hit.line, hit.end, parse)
    if on_line is not None:
        found.append(Candidate(on_line[0], hit.line, on_line[1], on_line[2], "line", hit.label))
    label_box = hit.box
    page_lines = [ln for ln in lines if ln.page == hit.line.page and ln is not hit.line]
    right = sorted(
        (ln for ln in page_lines if same_row(ln.box, label_box) and ln.box.x0 >= label_box.x1 - 4),
        key=lambda ln: ln.box.x0,
    )
    for line in right[:3]:
        value = _first(line, 0, parse)
        if value is not None:
            found.append(Candidate(value[0], line, value[1], value[2], "row", hit.label))
            break
    height = max(label_box.height, 8)
    under = sorted(
        (
            ln
            for ln in page_lines
            if label_box.y1 - height * 0.3 <= ln.box.y0 <= label_box.y1 + height * (below + 1.5)
            and ln.box.x0 < label_box.x1 + height * 2
            and ln.box.x1 > label_box.x0 - height
            and not same_row(ln.box, label_box)
        ),
        key=lambda ln: (ln.box.y0, abs(ln.box.x0 - label_box.x0)),
    )
    for line in under[:below]:
        value = _first(line, 0, parse)
        if value is not None:
            found.append(Candidate(value[0], line, value[1], value[2], "below", hit.label))
            break
    return found


def free[T](lines: Sequence[TextLine], parse: Parser[T]) -> list[Candidate[T]]:
    """Every match anywhere, in reading order, for fields that are recognisable without a
    label (an IBAN)."""
    found: list[Candidate[T]] = []
    for line in lines:
        for value, where in parse(line.text):
            found.append(Candidate(value, line, where.start, where.end, "free", None))
    return found
