"""Runtime state under var/<IČO>/: supplier memory, document counters, the feedback log and the
latest evaluation reports. `riso reset` copies data/initial_state over the first three, so
every demo starts from the same state; the evaluation does not depend on them."""

import shutil
from pathlib import Path

from riso import paths
from riso.contracts import Counters, EvalReport, Feedback, SupplierMemory

MEMORY_FILE = "supplier_memory.json"
COUNTERS_FILE = "counters.json"
FEEDBACK_FILE = "feedback.jsonl"


def eval_file(split: str) -> str:
    return f"eval-{split}.json"


class StateStore:
    def __init__(
        self, var_dir: Path | None = None, initial_dir: Path = paths.INITIAL_STATE_DIR
    ) -> None:
        self.var_dir = var_dir or paths.var_dir()
        self.initial_dir = initial_dir

    def entities(self) -> list[str]:
        """Entities with an initial state."""
        return sorted(d.name for d in self.initial_dir.iterdir() if d.is_dir())

    def reset(self) -> list[str]:
        """Restores every entity's memory and counters and clears its feedback log. Only the
        files the store owns are touched."""
        entities = self.entities()
        for ico in entities:
            target = self.var_dir / ico
            target.mkdir(parents=True, exist_ok=True)
            for name in (MEMORY_FILE, COUNTERS_FILE):
                shutil.copyfile(self.initial_dir / ico / name, target / name)
            (target / FEEDBACK_FILE).unlink(missing_ok=True)
        return entities

    def supplier_memory(self, ico: str) -> SupplierMemory:
        return SupplierMemory.model_validate_json(self._read(ico, MEMORY_FILE))

    def counters(self, ico: str) -> Counters:
        return Counters.model_validate_json(self._read(ico, COUNTERS_FILE))

    def save_supplier_memory(self, memory: SupplierMemory) -> None:
        self._write(memory.entity_ico, MEMORY_FILE, memory.model_dump_json(indent=2) + "\n")

    def save_counters(self, counters: Counters) -> None:
        self._write(counters.entity_ico, COUNTERS_FILE, counters.model_dump_json(indent=2) + "\n")

    def append_feedback(self, ico: str, feedback: Feedback) -> None:
        path = self.var_dir / ico / FEEDBACK_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log:
            log.write(feedback.model_dump_json() + "\n")

    def save_eval(self, report: EvalReport) -> Path:
        name = eval_file(report.split)
        self._write(report.entity_ico, name, report.model_dump_json(indent=2) + "\n")
        return self.var_dir / report.entity_ico / name

    def eval_report(self, ico: str, split: str) -> EvalReport | None:
        """The latest stored report of the split, or None before the first run."""
        path = self.var_dir / ico / eval_file(split)
        return EvalReport.model_validate_json(path.read_bytes()) if path.is_file() else None

    def _read(self, ico: str, name: str) -> bytes:
        """The runtime file, or the initial one before the first write or reset."""
        path = self.var_dir / ico / name
        return (path if path.is_file() else self.initial_dir / ico / name).read_bytes()

    def _write(self, ico: str, name: str, content: str) -> None:
        path = self.var_dir / ico / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
