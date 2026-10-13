"""The mock dataset: one DatasetCase per file, data/invoices/<split>/<case id>.json
(plan section 7)."""

from pathlib import Path

from riso import paths
from riso.contracts import DatasetCase

SPLITS = ("anchor", "seed", "heldout")

# Tags of DatasetCase: the family of the purchase, then the edge case it was built to test.
FAMILY_TAGS = (
    "energy", "water", "telecom", "post", "waste", "fuel", "materials", "it", "insurance",
    "membership", "training", "repairs", "services", "rent", "events", "kindergarten",
    "canteen", "capital",
)  # fmt: skip
EDGE_TAGS = ("split", "credit-note", "grant", "ocr-noise", "ambiguous", "precedent-trap")
TAGS = FAMILY_TAGS + EDGE_TAGS


def case_files(invoices_dir: Path = paths.INVOICES_DIR) -> list[Path]:
    return [path for split in SPLITS for path in sorted((invoices_dir / split).glob("*.json"))]


def load_case(path: Path) -> DatasetCase:
    case = DatasetCase.model_validate_json(path.read_bytes())
    if case.split != path.parent.name:
        raise ValueError(f"{path}: split {case.split!r}, but stored under {path.parent.name}/")
    if case.id != path.stem:
        raise ValueError(f"{path}: case id {case.id!r} differs from the file name")
    return case


def load_cases(invoices_dir: Path = paths.INVOICES_DIR) -> list[DatasetCase]:
    return [load_case(path) for path in case_files(invoices_dir)]
