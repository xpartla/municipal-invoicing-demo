"""The evaluation's files (it never reads the database or the runtime state): the supplier
memory and counters it starts from, `data/initial_state/<IČO>/`, and the reports `riso eval`
keeps in `var/<IČO>/eval-<split>.json` for `GET /api/eval` (until Vyhodnotenie moves into the
new UI, P2-M7). They replace the demo's `StateStore` (P2-M4-T10)."""

from pathlib import Path

from riso import paths
from riso.contracts import Counters, EvalReport, SupplierMemory

MEMORY_FILE = "supplier_memory.json"
COUNTERS_FILE = "counters.json"


def initial_memory(ico: str, root: Path = paths.INITIAL_STATE_DIR) -> SupplierMemory:
    return SupplierMemory.model_validate_json((root / ico / MEMORY_FILE).read_bytes())


def initial_counters(ico: str, root: Path = paths.INITIAL_STATE_DIR) -> Counters:
    return Counters.model_validate_json((root / ico / COUNTERS_FILE).read_bytes())


def report_path(ico: str, split: str, var_dir: Path | None = None) -> Path:
    return (var_dir or paths.var_dir()) / ico / f"eval-{split}.json"


def save_report(report: EvalReport, var_dir: Path | None = None) -> Path:
    path = report_path(report.entity_ico, report.split, var_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def load_report(ico: str, split: str, var_dir: Path | None = None) -> EvalReport | None:
    """The latest stored report of the split, or None before the first run."""
    path = report_path(ico, split, var_dir)
    return EvalReport.model_validate_json(path.read_bytes()) if path.is_file() else None
