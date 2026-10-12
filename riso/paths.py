"""Where the repository keeps its data, and where the raw exports live outside it."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
BUNDLES_DIR = DATA_DIR / "bundles"
ENTITIES_DIR = DATA_DIR / "entities"
INVOICES_DIR = DATA_DIR / "invoices"
INITIAL_STATE_DIR = DATA_DIR / "initial_state"
SCHEMAS_DIR = REPO_ROOT / "schemas"
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"
WEB_DIR = Path(__file__).resolve().parent / "web"


def raw_dir() -> Path:
    """The exports from the accounting software. They contain personal data, so they stay
    next to the repository, never inside it; RISO_RAW_DIR points elsewhere."""
    return Path(os.environ.get("RISO_RAW_DIR", REPO_ROOT.parent / "data"))


def var_dir() -> Path:
    """Runtime state: supplier memory, counters and feedback. Git-ignored."""
    return Path(os.environ.get("RISO_VAR_DIR", REPO_ROOT / "var"))
