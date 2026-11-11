"""The vendored fonts (testdata/fonts/, SIL Open Font License; sources in its README.md).

Every font a synthetic scan uses comes from here, so a page renders the same on every machine:
the body fonts through Chromium's @font-face, the handwriting through Pillow.
"""

from dataclasses import dataclass
from pathlib import Path

from riso import paths

FONTS_DIR = paths.TESTDATA_DIR / "fonts"


@dataclass(frozen=True, slots=True)
class BodyFont:
    family: str
    regular: str
    bold: str

    def files(self) -> tuple[Path, Path]:
        return FONTS_DIR / self.regular, FONTS_DIR / self.bold


# Faces like the ones Slovak invoices are printed in: a humanist sans (billing systems), a
# serif (a letter written in a word processor) and Calibri's metric twin (office documents).
BODY_FONTS = {
    "sans": BodyFont("PT Sans", "ptsans/PT_Sans-Web-Regular.ttf", "ptsans/PT_Sans-Web-Bold.ttf"),
    "serif": BodyFont(
        "PT Serif", "ptserif/PT_Serif-Web-Regular.ttf", "ptserif/PT_Serif-Web-Bold.ttf"
    ),
    "office": BodyFont("Carlito", "carlito/Carlito-Regular.ttf", "carlito/Carlito-Bold.ttf"),
}

HANDWRITING_FONTS = (
    "caveat/Caveat-wght.ttf",
    "kalam/Kalam-Regular.ttf",
    "patrickhand/PatrickHand-Regular.ttf",
    "indieflower/IndieFlower-Regular.ttf",
    "shadowsintolight/ShadowsIntoLight.ttf",
    "reeniebeanie/ReenieBeanie.ttf",
)

STAMP_FONT = BODY_FONTS["sans"].bold


def font_path(relative: str) -> Path:
    return FONTS_DIR / relative
