"""`riso ocr-eval` (plan §8.6): the OCR pipeline measured on a set of scans with their truth.

Each scan goes the extraction's way (its pages prepared, read by the reader, the fields
extracted, the note located and read for digits), and the report gives per field how often
it was found and right, the silent wrongs (a wrong value at confidence 0.6 or more, which the
check step would not mark), the time per page, how often the note's crop holds the note and
its two items were read, and the invoices that are right after the check step's automatic
fields (no silent wrong in them). It checks plan §8.6's targets.

The cases come from the CLI: the synthetic set from `riso.testdata` (which the application
does not import), or the four anchors from `../data`. A report on the anchors names the cases
and which fields were wrong, never a value read from them (they hold personal data).
"""

import datetime as dt
import hashlib
import math
import time
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from riso.contracts import InvoiceDocument
from riso.intake.application import DocumentReader, PageImage
from riso.intake.application.note import note_readings
from riso.intake.domain import MediaType, sniff
from riso.intake.domain.extract import DOUBTFUL, Context, FieldExtractor
from riso.intake.domain.layout import Box, DocumentLayout
from riso.intake.domain.note import read_note
from riso.intake.infrastructure.handwriting import InkLocator
from riso.intake.infrastructure.imaging import prepare_pages
from riso.intake.infrastructure.recorded import RecordedReader
from riso.intake.infrastructure.tesseract import TesseractReader
from riso.platform.settings import Settings

EvalSet = Literal["synthetic", "anchor"]
PRINTED = (
    "supplier.ico",
    "supplier.dic",
    "supplier.ic_dph",
    "supplier.iban",
    "customer.ico",
    "invoice.number",
    "invoice.issue_date",
    "invoice.delivery_date",
    "invoice.due_date",
    "invoice.variable_symbol",
    "totals.net",
    "totals.vat",
    "totals.gross",
)
TARGETS: dict[str, float] = {
    "supplier.ico": 0.95,
    "totals.gross": 0.95,
    "invoice.issue_date": 0.95,
    "invoice.variable_symbol": 0.85,
    "supplier.iban": 0.85,
}
SILENT_MAX = 0.02
SECONDS_PER_PAGE = 10.0
NOTE_HELD = 0.9


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    data: bytes
    truth: InvoiceDocument
    group: str | None = None
    """The synthetic layout, for the breakdown."""
    note_items: tuple[Box, ...] | None = None
    """The handwritten date's and number's boxes in the scan's pixels (synthetic only)."""
    scan_size: tuple[int, int] | None = None
    scan_dpi: int | None = None
    exclude: frozenset[str] = frozenset()
    """Fields the truth cannot say (an anchor's personal data, made up in the repository)."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldScore(_Model):
    field: str
    present: int
    """Cases whose truth has the field."""
    found: int
    right: int
    silent: int
    accuracy: float | None
    found_rate: float | None


class Target(_Model):
    metric: str
    target: float
    value: float | None
    met: bool
    upper: bool = False
    """The value must stay at or under the target (silent wrong, time)."""
    gating: bool = True
    """Whether missing it fails `--strict` (plan §8.6's targets do); the note's crop is
    reported only (P2-M5-T06 asked for 90%)."""


class CaseResult(_Model):
    id: str
    group: str | None
    pages: int
    seconds: float
    wrong: list[str]
    silent: list[str]
    note_held: bool | None


class NoteScore(_Model):
    cases: int
    measured: int
    """Cases whose note's position is known (the synthetic set)."""
    held: int
    date_read: int
    number_read: int


class OcrEvalReport(_Model):
    set: EvalSet
    engine: str
    engine_version: str
    generated_at: dt.datetime
    cases: int
    pages: int
    seconds_per_page: float
    fields: list[FieldScore]
    printed_filled: int
    silent: int
    silent_rate: float
    right_after_check: int
    note: NoteScore
    targets: list[Target]
    results: list[CaseResult]

    @property
    def met(self) -> bool:
        return all(t.met for t in self.targets if t.gating)


def _value(document: InvoiceDocument, path: str) -> Any:
    part, name = path.split(".")
    value = getattr(getattr(document, part), name)
    if path == "supplier.iban" and value:
        return "".join(value.split()).upper()
    return value


def _on_page(box: Box, page: PageImage, size: tuple[int, int], render: float) -> Box:
    """A box of the scan on the prepared page: rendered (a PDF), enlarged, turned."""
    scale = page.scale * render
    angle = math.radians(page.angle)
    width, height = size[0] * scale, size[1] * scale
    cx, cy = page.image.width / 2, page.image.height / 2
    points = []
    for x, y in ((box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1)):
        dx, dy = x * scale - width / 2, y * scale - height / 2
        points.append(
            (
                cx + dx * math.cos(angle) + dy * math.sin(angle),
                cy - dx * math.sin(angle) + dy * math.cos(angle),
            )
        )
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return Box(math.floor(min(xs)), math.floor(min(ys)), math.ceil(max(xs)), math.ceil(max(ys)))


def _held(items: Sequence[Box], crop: Box) -> bool:
    def share(item: Box) -> float:
        part = item.intersection(crop)
        return 0.0 if part is None else part.area / max(1, item.area)

    return all(share(item) >= 0.85 for item in items)


def evaluate(
    cases: Iterable[EvalCase],
    reader: DocumentReader,
    *,
    eval_set: EvalSet,
    customer: Context,
    now: dt.datetime,
) -> OcrEvalReport:
    extractor = FieldExtractor()
    locator = InkLocator()
    present = dict.fromkeys(PRINTED, 0)
    found = dict.fromkeys(PRINTED, 0)
    right = dict.fromkeys(PRINTED, 0)
    silent = dict.fromkeys(PRINTED, 0)
    results: list[CaseResult] = []
    pages_total, seconds_total = 0, 0.0
    note = {"measured": 0, "held": 0, "date": 0, "number": 0}
    right_after = 0
    filled = 0
    for case in cases:
        media_type = sniff(case.data)
        if not isinstance(media_type, MediaType):
            raise ValueError(f"{case.id} is not a document the intake takes")
        started = time.perf_counter()
        pages = prepare_pages(case.data, media_type, hashlib.sha256(case.data).hexdigest())
        layouts = [reader.read(page) for page in pages]
        extracted = extractor.extract(
            DocumentLayout(tuple(layouts), reader.engine, reader.version),
            document_id="evaluation",
            context=customer,
        )
        region, readings = note_readings(pages[0], layouts[0], locator, reader)
        seconds = time.perf_counter() - started
        pages_total += len(pages)
        seconds_total += seconds

        document = extracted.document
        confidence = document.ocr_meta.confidence
        wrong, quiet = [], []
        for path in PRINTED:
            if path in case.exclude:
                continue
            expected, got = _value(case.truth, path), _value(document, path)
            if expected is not None:
                present[path] += 1
                if got is not None:
                    found[path] += 1
                if got == expected:
                    right[path] += 1
            if got is not None:
                filled += 1
            if got is not None and got != expected:
                wrong.append(path)
                if confidence.get(path, 0.0) >= DOUBTFUL:
                    silent[path] += 1
                    quiet.append(path)
            elif got is None and expected is not None:
                wrong.append(path)
        right_after += not quiet

        held: bool | None = None
        if case.note_items is not None and case.scan_size is not None:
            render = 300 / case.scan_dpi if media_type is MediaType.PDF and case.scan_dpi else 1.0
            items = [_on_page(b, pages[0], case.scan_size, render) for b in case.note_items]
            held = _held(items, region.box) if items else None
            if held is not None:
                note["measured"] += 1
                note["held"] += held
        dates, numbers = read_note(readings)
        written = case.truth.handwritten
        note["date"] += written.date is not None and written.date in dates[:1]
        note["number"] += written.number is not None and str(int(written.number)) in numbers[:1]
        results.append(
            CaseResult(
                id=case.id,
                group=case.group,
                pages=len(pages),
                seconds=round(seconds, 2),
                wrong=wrong,
                silent=quiet,
                note_held=held,
            )
        )

    fields = [
        FieldScore(
            field=path,
            present=present[path],
            found=found[path],
            right=right[path],
            silent=silent[path],
            accuracy=round(right[path] / present[path], 4) if present[path] else None,
            found_rate=round(found[path] / present[path], 4) if present[path] else None,
        )
        for path in PRINTED
    ]
    silent_total = sum(silent.values())
    per_page = seconds_total / pages_total if pages_total else 0.0
    by_field = {f.field: f for f in fields}
    targets = [
        Target(
            metric=path,
            target=goal,
            value=by_field[path].accuracy,
            met=(by_field[path].accuracy or 0) >= goal,
        )
        for path, goal in TARGETS.items()
    ]
    rate = silent_total / filled if filled else 0.0
    targets.append(
        Target(
            metric="silent_rate",
            target=SILENT_MAX,
            value=round(rate, 4),
            met=rate <= SILENT_MAX,
            upper=True,
        )
    )
    targets.append(
        Target(
            metric="seconds_per_page",
            target=SECONDS_PER_PAGE,
            value=round(per_page, 2),
            met=per_page < SECONDS_PER_PAGE,
            upper=True,
        )
    )
    if note["measured"]:
        share = note["held"] / note["measured"]
        targets.append(
            Target(
                metric="note_held",
                target=NOTE_HELD,
                value=round(share, 4),
                met=share >= NOTE_HELD,
                gating=False,
            )
        )
    return OcrEvalReport(
        set=eval_set,
        engine=reader.engine,
        engine_version=reader.version,
        generated_at=now,
        cases=len(results),
        pages=pages_total,
        seconds_per_page=round(per_page, 2),
        fields=fields,
        printed_filled=filled,
        silent=silent_total,
        silent_rate=round(rate, 4),
        right_after_check=right_after,
        note=NoteScore(
            cases=len(results),
            measured=note["measured"],
            held=note["held"],
            date_read=note["date"],
            number_read=note["number"],
        ),
        targets=targets,
        results=results,
    )


# The four anchors (`../data/FA.xlsx`) ---------------------------------------------------------

ANCHOR_IMAGES = {
    "xl/media/image3.png": "anchor-accounting",
    "xl/media/image6.png": "anchor-telekom",
    "xl/media/image9.png": "anchor-dpo",
    "xl/media/image12.png": "anchor-dog-shelter",
}
"""The scans in the workbook, by the cases they are (checked by their handwritten numbers)."""
ADDRESSED_TO = "00305111"
"""The scans are addressed to Obec Štefanová; the committed cases are re-addressed to Boldog."""
MADE_UP = {
    "anchor-accounting": frozenset(
        {"supplier.ico", "supplier.dic", "supplier.ic_dph", "supplier.iban"}
    )
}
"""The sole trader's identity is made up in the repository (a natural person)."""


def anchor_cases(workbook: Path, invoices: Path) -> list[EvalCase]:
    """The four anchor scans with their committed cases, customer IČO as on the scans. The
    scans are read here and never written anywhere."""
    from riso.dataset import load_case

    cases = []
    with zipfile.ZipFile(workbook) as book:
        for member, case_id in ANCHOR_IMAGES.items():
            case = load_case(invoices / "anchor" / f"{case_id}.json")
            customer = case.invoice.customer.model_copy(update={"ico": ADDRESSED_TO})
            truth = case.invoice.model_copy(update={"customer": customer})
            cases.append(
                EvalCase(
                    id=case_id,
                    data=book.read(member),
                    truth=truth,
                    exclude=MADE_UP.get(case_id, frozenset()),
                )
            )
    return cases


def format_report(report: OcrEvalReport) -> str:
    lines = [
        f"{report.set}: {report.cases} cases, {report.pages} pages, {report.engine} "
        f"{report.engine_version}, {report.seconds_per_page:.2f} s a page",
        "",
        f"{'field':26} {'right':>9} {'found':>9} {'silent':>7}",
    ]
    for f in report.fields:
        if not f.present and not f.silent:
            continue
        accuracy = f"{f.accuracy:.0%}" if f.accuracy is not None else "-"
        found = f"{f.found_rate:.0%}" if f.found_rate is not None else "-"
        lines.append(
            f"{f.field:26} {f.right:>3}/{f.present:<3} {accuracy:>4} {found:>9} {f.silent:>7}"
        )
    lines += [
        "",
        f"silent wrong: {report.silent} of {report.printed_filled} printed fields filled "
        f"({report.silent_rate:.1%})",
        f"right after the check step's automatic fields: {report.right_after_check} of "
        f"{report.cases} invoices",
        f"note: crop holds it {report.note.held}/{report.note.measured}; read: date "
        f"{report.note.date_read}, number {report.note.number_read} of {report.note.cases}"
        + (" (handwriting in a font: optimistic)" if report.set == "synthetic" else ""),
        "",
        "targets:",
    ]
    for t in report.targets:
        sign = "≤" if t.upper else "≥"
        mark = "ok" if t.met else ("MISSED" if t.gating else "below")
        note = "" if t.gating else "  (reported, not a plan §8.6 target)"
        lines.append(f"  {mark:6} {t.metric:24} {t.value} {sign} {t.target}{note}")
    return "\n".join(lines)


def synthetic_case(
    case_id: str,
    data: bytes,
    truth: InvoiceDocument,
    *,
    group: str,
    note_boxes: Iterable[tuple[int, int, int, int]],
    scan_size: tuple[int, int],
    scan_dpi: int,
) -> EvalCase:
    return EvalCase(
        id=case_id,
        data=data,
        truth=truth,
        group=group,
        note_items=tuple(Box(*box) for box in note_boxes),
        scan_size=scan_size,
        scan_dpi=scan_dpi,
    )


def run(
    cases: Iterable[EvalCase], settings: Settings, eval_set: EvalSet, now: dt.datetime
) -> OcrEvalReport:
    """The evaluation with the configured reader (`RISO_OCR_READER`), as Boldog."""
    assert settings.tessdata is not None
    reader: DocumentReader = (
        RecordedReader(settings.ocr_recordings)
        if settings.ocr_reader == "recorded"
        else TesseractReader(settings.tessdata)
    )
    try:
        return evaluate(
            cases,
            reader,
            eval_set=eval_set,
            customer=Context(customer_ico="00305863", customer_name="Obec Boldog"),
            now=now,
        )
    finally:
        if isinstance(reader, TesseractReader):
            reader.close()
