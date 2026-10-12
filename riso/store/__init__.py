"""Runtime state under var/<IČO>/: supplier memory, document counters and the feedback log.
`riso reset` copies data/initial_state over it, so every demo starts from the same state."""

import shutil
from pathlib import Path

from riso import paths
from riso.contracts import Counters, Feedback, SupplierMemory

MEMORY_FILE = "supplier_memory.json"
COUNTERS_FILE = "counters.json"
FEEDBACK_FILE = "feedback.jsonl"


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

    def _read(self, ico: str, name: str) -> bytes:
        """The runtime file, or the initial one before the first write or reset."""
        path = self.var_dir / ico / name
        return (path if path.is_file() else self.initial_dir / ico / name).read_bytes()

    def _write(self, ico: str, name: str, content: str) -> None:
        path = self.var_dir / ico / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
