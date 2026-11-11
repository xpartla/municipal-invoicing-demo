"""`riso testdata scans`: the synthetic scan set (plan §8.6, P2-M5-T01).

Each of the 70 seed and held-out cases is rendered through its supplier's layout in headless
Chromium (Python Playwright), as a 300-dpi page image and as a digital PDF with a text layer.
The handwritten note and the approval stamp are drawn on the image, which then gets the
case's capture damage. Per case the output directory holds:

- `<case>.scan.<jpg|png|pdf>`: the photo or scan;
- `<case>.digital.pdf`: the invoice as a billing system would send it (no note);
- `<case>.truth.json`: a `ScanTruth`;

and `manifest.json` lists the seed and every file's SHA-256. The same seed gives the same
bytes on a machine with the same Chromium build: fonts are vendored, the page is served from
memory with no network, Chromium's PDF dates are fixed and every random choice is seeded.

About ten cases are committed as samples (`testdata/ocr/samples/`); the rest is generated
into `testdata/ocr/generated/` (git-ignored), in CI and locally.
"""

import hashlib
import io
import json
import re
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from riso import paths
from riso.contracts import DatasetCase
from riso.dataset import load_cases
from riso.testdata import augment, handwriting, layouts
from riso.testdata.fonts import FONTS_DIR
from riso.testdata.truth import LayoutName, ScanTruth

if TYPE_CHECKING:
    from playwright.sync_api import Page, Route, ViewportSize

DEFAULT_SEED = 2026
GENERATED_DIR = paths.TESTDATA_DIR / "ocr" / "generated"
SAMPLES_DIR = paths.TESTDATA_DIR / "ocr" / "samples"
SPLITS = ("seed", "heldout")

# The committed samples: every layout, photos and scans in each format, a credit note, cases
# with OCR noise, a split and long and short invoices; about 2.4 MB in all.
SAMPLE_CASES: tuple[str, ...] = (
    "heldout-04-vzorova-accounting",  # classic, grayscale PNG scan, not a VAT payer
    "heldout-07-hornbach-kd",  # grid, photo, seven lines
    "heldout-10-bvs-water-ocu-noise",  # grid, photo, the handwritten date unreadable (absent)
    "heldout-12-orange-mobile-ocu",  # classic, photo at 95 dpi, the note stacked
    "heldout-16-ozpomoc-noise",  # modern, PDF scan, a misread IČO failing its check digit
    "heldout-19-telekom-phone",  # modern, grayscale JPEG scan
    "heldout-23-zse-ocu-ms",  # bill, photo, fourteen lines split by building
    "heldout-35-metro-credit-note",  # classic, PDF scan, a credit note
    "seed-04-fcc-waste",  # bill, grayscale PDF scan
    "seed-12-zmos-membership",  # modern, photo, the number in the margin
)

_ORIGIN = "https://testdata.invalid"
_FONT_URL = f"{_ORIGIN}/fonts"
# A4 at 96 CSS pixels per inch, drawn at 300 dpi.
_VIEWPORT: "ViewportSize" = {"width": 794, "height": 1123}
_SCALE = 300 / 96
_PDF_DATE = re.compile(rb"\(D:\d{14}[^)]*\)")
_FIXED_PDF_DATE = b"(D:20260101000000+00'00')"
EXTENSIONS = {"jpeg": "jpg", "png": "png", "pdf": "pdf"}


def dataset_cases() -> list[DatasetCase]:
    """The 70 cases scans are made of (plan §8.6): the seed and held-out sets. The anchors
    are real scans and are measured from `../data` instead."""
    return [case for case in load_cases() if case.split in SPLITS]


@dataclass(frozen=True, slots=True)
class Rendered:
    png: bytes
    pdf: bytes
    fit: float


class Renderer:
    """One Chromium page, reused for every case."""

    def __init__(self, page: "Page") -> None:
        self._page = page
        self._html = ""
        page.route("**/*", self._serve)

    def _serve(self, route: "Route") -> None:
        url = route.request.url
        if url == f"{_ORIGIN}/page.html":
            route.fulfill(body=self._html, content_type="text/html; charset=utf-8")
        elif url.startswith(f"{_FONT_URL}/"):
            path = (FONTS_DIR / url.removeprefix(f"{_FONT_URL}/")).resolve()
            if FONTS_DIR.resolve() in path.parents and path.is_file():
                route.fulfill(body=path.read_bytes(), content_type="font/ttf")
            else:
                route.abort()
        else:
            route.abort()

    def render(self, html_text: str) -> Rendered:
        """The page at 300 dpi and as a PDF. A page whose content overflows A4 is printed a
        little smaller, as a billing system would fit a long invoice."""
        self._html = html_text
        page = self._page
        page.goto(f"{_ORIGIN}/page.html")
        page.evaluate("document.fonts.ready")
        fit = 1.0
        while fit > 0.6 and page.evaluate(
            "() => { const c = document.querySelector('.content');"
            " return c.scrollHeight > c.clientHeight + 1; }"
        ):
            fit = round(fit - 0.04, 2)
            page.evaluate(f"document.documentElement.style.setProperty('--fit', '{fit}')")
        png = page.screenshot(type="png")
        pdf = page.pdf(
            format="A4",
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        return Rendered(png=png, pdf=_PDF_DATE.sub(_fixed_date, pdf), fit=fit)


def _fixed_date(match: re.Match[bytes]) -> bytes:
    """Chromium stamps the PDF with the time; the same length keeps the offsets valid."""
    return _FIXED_PDF_DATE[: len(match.group(0))].ljust(len(match.group(0)), b" ")


@contextmanager
def chromium() -> Iterator[Renderer]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - the dev group is missing
        raise RuntimeError(
            "riso testdata needs Python Playwright (uv sync installs the dev group) and its "
            "Chromium (uv run playwright install chromium)"
        ) from exc
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport=_VIEWPORT, device_scale_factor=_SCALE)
        try:
            yield Renderer(context.new_page())
        finally:
            browser.close()


def generate_case(
    case: DatasetCase, layout: LayoutName, seed: int, renderer: Renderer
) -> tuple[ScanTruth, dict[str, bytes]]:
    """One case's files (by name) and its truth."""
    document = case.invoice
    rendered = renderer.render(_page_html(case, layout, seed))

    page = Image.open(io.BytesIO(rendered.png)).convert("RGB")
    note = handwriting.draw_note(page, document, layouts.derive(seed, "note", case.id))
    stamp = handwriting.draw_stamp(page, layouts.derive(seed, "stamp", case.id))
    boxes = {"stamp": stamp} if stamp else {}
    if note.date:
        boxes["date"] = note.date.box
    if note.number:
        boxes["number"] = note.number.box
    scan, info, moved = augment.capture(page, layouts.derive(seed, "capture", case.id), boxes)

    scan_name = f"{case.id}.scan.{EXTENSIONS[info.format]}"
    pdf_name = f"{case.id}.digital.pdf"
    truth = ScanTruth(
        case_id=case.id,
        split=case.split,
        seed=seed,
        layout=layout,
        files={"scan": scan_name, "digital_pdf": pdf_name},
        capture=info,
        handwriting=note.model_copy(
            update={
                "date": note.date.model_copy(update={"box": moved["date"]}) if note.date else None,
                "number": note.number.model_copy(update={"box": moved["number"]})
                if note.number
                else None,
            }
        ),
        stamp=moved.get("stamp"),
        document=document,
    )
    files = {
        scan_name: scan,
        pdf_name: rendered.pdf,
        f"{case.id}.truth.json": (truth.model_dump_json(indent=2) + "\n").encode(),
    }
    return truth, files


def _page_html(case: DatasetCase, layout: LayoutName, seed: int) -> str:
    document = case.invoice
    style = layouts.style_for(layouts.supplier_key(document), layout, seed)
    extras = layouts.extras_for(document, layout, seed)
    return layouts.page_html(document, style, extras, _FONT_URL)


def digital_pdfs(cases: Sequence[DatasetCase], seed: int = DEFAULT_SEED) -> dict[str, bytes]:
    """Each case's digital PDF by case ID, the same bytes `generate` writes as
    `<case>.digital.pdf`, without rendering the scans (the e-invoices attach their XML to it)."""
    assigned = layouts.assign_layouts(
        (layouts.supplier_key(c.invoice) for c in dataset_cases()), seed
    )
    with chromium() as renderer:
        return {
            case.id: renderer.render(
                _page_html(case, assigned[layouts.supplier_key(case.invoice)], seed)
            ).pdf
            for case in cases
        }


def generate(
    out: Path,
    *,
    seed: int = DEFAULT_SEED,
    only: Sequence[str] | None = None,
    progress: bool = False,
) -> list[ScanTruth]:
    """Write the scans of the dataset's cases (or of the case IDs in `only`) into `out`,
    replacing what was there, and the manifest."""
    cases = dataset_cases()
    known = {case.id for case in cases}
    unknown = sorted(set(only or ()) - known)
    if unknown:
        raise ValueError(f"no seed or held-out case {', '.join(unknown)}")
    # Layouts are assigned over every supplier, so a subset gets the layouts the full set has.
    assigned = layouts.assign_layouts((layouts.supplier_key(c.invoice) for c in cases), seed)
    chosen = [case for case in cases if only is None or case.id in only]

    out.mkdir(parents=True, exist_ok=True)
    for stale in out.iterdir():
        if stale.is_file() and stale.name.split(".")[0] in known | {"manifest"}:
            stale.unlink()
    truths = []
    digests: dict[str, dict[str, str]] = {}
    with chromium() as renderer:
        for i, case in enumerate(chosen, start=1):
            layout = assigned[layouts.supplier_key(case.invoice)]
            truth, files = generate_case(case, layout, seed, renderer)
            for name, data in files.items():
                (out / name).write_bytes(data)
            digests[case.id] = {
                name: hashlib.sha256(data).hexdigest() for name, data in files.items()
            }
            truths.append(truth)
            if progress:
                print(f"  {i:2d}/{len(chosen)}  {case.id}  {layout}  {truth.files['scan']}")
    manifest = {"seed": seed, "cases": digests}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return truths


def load_truths(directory: Path) -> list[ScanTruth]:
    return [
        ScanTruth.model_validate_json(path.read_bytes())
        for path in sorted(directory.glob("*.truth.json"))
    ]


def sizes(directory: Path, names: Iterable[str] | None = None) -> int:
    files = [directory / n for n in names] if names else list(directory.iterdir())
    return sum(f.stat().st_size for f in files if f.is_file())
