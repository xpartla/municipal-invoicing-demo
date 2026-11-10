"""The page layout (plan §8.3): what an OCR engine, or a PDF's text layer, saw on a page:
words with their boxes and confidences, grouped into lines and blocks. It does not depend on
the engine, so the field extractor reads the same structure from Tesseract today and from
Azure Document Intelligence later.

Coordinates are pixels of the page image the reading was made on (the normalised page the
check step shows), origin top left; confidences are 0–1.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from riso.shared.errors import DomainError


class ReadingFailed(DomainError):
    """A page could not be read: the reason's code (`no_recording`, `ocr_failed`, …)."""

    def __init__(self, reason: str, message: str | None = None) -> None:
        super().__init__(message or reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Box:
    """Left, top, right, bottom; right and bottom exclusive."""

    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    @property
    def centre(self) -> tuple[float, float]:
        return (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2

    def union(self, other: "Box") -> "Box":
        return Box(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )

    def intersection(self, other: "Box") -> "Box | None":
        box = Box(
            max(self.x0, other.x0),
            max(self.y0, other.y0),
            min(self.x1, other.x1),
            min(self.y1, other.y1),
        )
        return box if box.width > 0 and box.height > 0 else None

    def contains(self, other: "Box") -> bool:
        return (
            self.x0 <= other.x0
            and self.y0 <= other.y0
            and other.x1 <= self.x1
            and other.y1 <= self.y1
        )

    def grown(self, by: int) -> "Box":
        return Box(self.x0 - by, self.y0 - by, self.x1 + by, self.y1 + by)

    def scaled(self, factor: float) -> "Box":
        return Box(
            round(self.x0 * factor),
            round(self.y0 * factor),
            round(self.x1 * factor),
            round(self.y1 * factor),
        )

    def to_list(self) -> list[int]:
        return [self.x0, self.y0, self.x1, self.y1]

    @classmethod
    def of(cls, values: Iterable[int]) -> "Box":
        x0, y0, x1, y1 = (int(v) for v in values)
        return cls(x0, y0, x1, y1)

    @classmethod
    def around(cls, boxes: Iterable["Box"]) -> "Box | None":
        result: Box | None = None
        for box in boxes:
            result = box if result is None else result.union(box)
        return result


@dataclass(frozen=True, slots=True)
class Word:
    text: str
    box: Box
    confidence: float
    block: int
    line: int
    """The line's number on the page; words of one line share it."""


@dataclass(frozen=True, slots=True)
class Line:
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def box(self) -> Box:
        box = Box.around(word.box for word in self.words)
        assert box is not None  # a line has words
        return box

    @property
    def confidence(self) -> float:
        return sum(word.confidence for word in self.words) / len(self.words)

    @property
    def block(self) -> int:
        return self.words[0].block


@dataclass(frozen=True, slots=True)
class PageLayout:
    index: int
    """The page's number in the document, from 0."""
    width: int
    height: int
    dpi: int
    words: tuple[Word, ...]
    source: str = "ocr"
    """`ocr`, or `text_layer` for a digital PDF's words."""

    def lines(self) -> list[Line]:
        """The words grouped by line, in reading order (the order the words came in)."""
        grouped: dict[int, list[Word]] = {}
        for word in self.words:
            grouped.setdefault(word.line, []).append(word)
        return [Line(tuple(words)) for words in grouped.values()]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines())

    def to_json(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "width": self.width,
            "height": self.height,
            "dpi": self.dpi,
            "source": self.source,
            "words": [
                [w.text, w.box.to_list(), round(w.confidence, 4), w.block, w.line]
                for w in self.words
            ],
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "PageLayout":
        return cls(
            index=int(data["index"]),
            width=int(data["width"]),
            height=int(data["height"]),
            dpi=int(data["dpi"]),
            source=str(data.get("source", "ocr")),
            words=tuple(
                Word(str(text), Box.of(box), float(conf), int(block), int(line))
                for text, box, conf, block, line in data["words"]
            ),
        )


@dataclass(frozen=True, slots=True)
class DocumentLayout:
    """Every page of a document as read, and by which engine."""

    pages: tuple[PageLayout, ...]
    engine: str
    engine_version: str

    def to_json(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "engine_version": self.engine_version,
            "pages": [page.to_json() for page in self.pages],
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "DocumentLayout":
        return cls(
            engine=str(data["engine"]),
            engine_version=str(data["engine_version"]),
            pages=tuple(PageLayout.from_json(page) for page in data["pages"]),
        )
