"""What a synthetic scan shows: the truth file written next to it (`<case>.truth.json`).

`document` is the dataset case's `InvoiceDocument`, exactly what the layout printed; the
handwritten note and the approval stamp are located in the scan's pixels, so the handwriting
locator and the OCR evaluation can be measured against them.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from riso.contracts import InvoiceDocument

LayoutName = Literal["bill", "modern", "classic", "grid"]
LAYOUT_NAMES: tuple[LayoutName, ...] = ("bill", "modern", "classic", "grid")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Box(_Model):
    """A rectangle in pixels of the image it belongs to: left, top, right, bottom (exclusive)."""

    x0: int
    y0: int
    x1: int
    y1: int

    def contains(self, other: "Box") -> bool:
        return (
            self.x0 <= other.x0
            and self.y0 <= other.y0
            and other.x1 <= self.x1
            and other.y1 <= self.y1
        )

    def union(self, other: "Box") -> "Box":
        return Box(
            x0=min(self.x0, other.x0),
            y0=min(self.y0, other.y0),
            x1=max(self.x1, other.x1),
            y1=max(self.y1, other.y1),
        )


class Capture(_Model):
    """How the page was "photographed" or "scanned" (the seeded damage)."""

    mode: Literal["photo", "scanner"]
    format: Literal["jpeg", "png", "pdf"]
    dpi: int = Field(description="Pixels per inch of the page in the scan")
    width: int
    height: int
    grayscale: bool
    rotation: float = Field(description="Degrees, counter-clockwise")
    perspective: float = Field(description="Largest corner displacement, in pixels")
    blur: float = Field(description="Gaussian blur radius, in pixels of the scan")
    noise: float = Field(description="Standard deviation of the added noise, 0–255")
    jpeg_quality: int | None
    page: list[tuple[float, float]] = Field(
        description="The page's corners in the scan: top left, top right, bottom right, bottom left"
    )


class Note(_Model):
    """One handwritten item of the note, where the scan shows it."""

    text: str
    box: Box


class Handwriting(_Model):
    font: str
    placement: Literal["split", "stacked", "inline", "margin"]
    date: Note | None
    number: Note | None

    def box(self) -> Box | None:
        boxes = [note.box for note in (self.date, self.number) if note is not None]
        if not boxes:
            return None
        union = boxes[0]
        for box in boxes[1:]:
            union = union.union(box)
        return union


class ScanTruth(_Model):
    case_id: str
    split: str
    seed: int
    layout: LayoutName
    files: dict[Literal["scan", "digital_pdf"], str]
    capture: Capture
    handwriting: Handwriting
    stamp: Box | None = Field(description="The approval stamp, blue ink like the note")
    document: InvoiceDocument
