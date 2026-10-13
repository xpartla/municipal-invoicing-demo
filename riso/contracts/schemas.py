"""JSON Schema export of the contracts. The files in schemas/ are generated from here, and a
test fails when they drift from the models."""

import json
from pathlib import Path

from pydantic import BaseModel

from riso.contracts.context import EntityContext
from riso.contracts.dataset import DatasetCase
from riso.contracts.eval import EvalReport
from riso.contracts.feedback import Feedback
from riso.contracts.invoice import InvoiceDocument
from riso.contracts.proposal import CodeRequest, CodingProposal
from riso.contracts.reference import ReferenceBundle
from riso.contracts.state import Counters, SupplierMemory

SCHEMAS: dict[str, type[BaseModel]] = {
    "invoice-document": InvoiceDocument,
    "reference-bundle": ReferenceBundle,
    "coding-proposal": CodingProposal,
    "code-request": CodeRequest,
    "feedback": Feedback,
    "entity-context": EntityContext,
    "dataset-case": DatasetCase,
    "supplier-memory": SupplierMemory,
    "counters": Counters,
    "eval-report": EvalReport,
}


def render_schemas() -> dict[str, str]:
    """File name to file content, one schema per contract."""
    rendered = {}
    for name, model in SCHEMAS.items():
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            **model.model_json_schema(),
        }
        rendered[f"{name}.schema.json"] = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    return rendered


def write_schemas(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for file_name, content in render_schemas().items():
        path = directory / file_name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def stale_schemas(directory: Path) -> list[str]:
    """Schema files that are missing or differ from what the models produce."""
    return [
        file_name
        for file_name, content in render_schemas().items()
        if not (directory / file_name).is_file()
        or (directory / file_name).read_text(encoding="utf-8") != content
    ]
