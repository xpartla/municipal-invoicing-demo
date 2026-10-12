"""Command line: riso ingest | check | export-schemas | reset | serve | code | eval."""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from riso import paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="riso", description="Invoice coding demo for Slovak municipalities"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="build a reference bundle from the Excel exports")
    ingest.add_argument(
        "--raw", type=Path, help="directory with the exports (default ../data, or RISO_RAW_DIR)"
    )
    ingest.add_argument("--out", type=Path, default=paths.BUNDLES_DIR)

    commands.add_parser("check", help="check the committed data against the dictionaries")

    schemas = commands.add_parser("export-schemas", help="write the contracts as JSON Schema")
    schemas.add_argument("--out", type=Path, default=paths.SCHEMAS_DIR)
    schemas.add_argument("--check", action="store_true", help="only report stale files")

    commands.add_parser("reset", help="restore the runtime state from data/initial_state")

    serve = commands.add_parser("serve", help="run the API and the pages")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    code = commands.add_parser("code", help="propose the coding of one InvoiceDocument")
    code.add_argument("invoice", type=Path, help="InvoiceDocument or DatasetCase JSON")

    commands.add_parser("eval", help="evaluate the held-out set")

    args = parser.parse_args(argv)
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "ingest": _ingest,
        "check": _check,
        "export-schemas": _export_schemas,
        "reset": _reset,
        "serve": _serve,
        "code": _code,
        "eval": _eval,
    }
    return handlers[args.command](args)


def _ingest(args: argparse.Namespace) -> int:
    from riso.ingest import IngestError, build_bundle, write_bundle

    raw = args.raw or paths.raw_dir()
    try:
        bundle = build_bundle(raw)
    except IngestError as exc:
        print(f"riso ingest: {exc}", file=sys.stderr)
        return 1
    path = write_bundle(bundle, args.out)
    print(f"{bundle.bundle_id}  {bundle.entity.name}, from {raw}")
    print(
        f"  {len(bundle.accounts)} accounts, {len(bundle.budget_positions_expense)} expense and "
        f"{len(bundle.budget_positions_income)} income positions, "
        f"{len(bundle.document_series)} document series, {len(bundle.transfers)} mock transfers"
    )
    for warning in bundle.warnings:
        rows = ", ".join(str(r) for r in warning.rows)
        print(f"  warning  {warning.source} rows {rows}: {warning.message}")
    print(f"wrote {_shown(path)}")
    return 0


def _check(args: argparse.Namespace) -> int:
    from riso.checks import run_checks

    results = run_checks()
    for result in results:
        print(f"{'FAIL' if result.errors else 'ok  '}  {result.name}")
        for error in result.errors:
            print(f"        {error}")
    failed = sum(1 for r in results if r.errors)
    print(f"{len(results) - failed} of {len(results)} checks passed")
    return 1 if failed else 0


def _export_schemas(args: argparse.Namespace) -> int:
    from riso.contracts.schemas import stale_schemas, write_schemas

    if args.check:
        stale = stale_schemas(args.out)
        for name in stale:
            print(f"stale  {name}")
        return 1 if stale else 0
    for path in write_schemas(args.out):
        print(f"wrote {_shown(path)}")
    return 0


def _reset(args: argparse.Namespace) -> int:
    from riso.store import StateStore

    store = StateStore()
    entities = store.reset()
    print(f"restored {', '.join(entities)} in {_shown(store.var_dir)}")
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "riso.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def _code(args: argparse.Namespace) -> int:
    import json

    from riso.contracts import DatasetCase, InvoiceDocument
    from riso.engine import code_invoice
    from riso.knowledge import load_knowledge
    from riso.reference import LocalReferenceSource
    from riso.store import StateStore

    data = json.loads(args.invoice.read_text(encoding="utf-8"))
    document = (
        DatasetCase.model_validate(data).invoice
        if "expected" in data
        else InvoiceDocument.model_validate(data)
    )
    ico = "".join((document.customer.ico or "").split())
    references, state = LocalReferenceSource(), StateStore()
    try:
        entity = references.context(ico)
        proposal = code_invoice(
            document,
            entity=entity,
            bundle=references.bundle(ico, entity.reference_period),
            memory=state.supplier_memory(ico),
            counters=state.counters(ico),
            knowledge=load_knowledge(entity.budget_year),
        )
    except (LookupError, NotImplementedError) as exc:
        print(f"riso code: {exc}", file=sys.stderr)
        return 2
    print(proposal.model_dump_json(indent=2))
    return 0


def _eval(args: argparse.Namespace) -> int:
    from riso.dataset import load_cases
    from riso.eval import evaluate

    try:
        metrics = evaluate([c for c in load_cases() if c.split == "heldout"])
    except NotImplementedError as exc:
        print(f"riso eval: {exc}", file=sys.stderr)
        return 2
    for name, value in metrics.items():
        print(f"{name:32} {value:.3f}")
    return 0


def _shown(path: Path) -> str:
    """The path relative to the working directory when it is below it."""
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
