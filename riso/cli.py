"""Command line: riso ingest | check | export-schemas | export-openapi | reset | serve | code |
eval | migrate | worker."""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from riso import paths
from riso.shared.errors import DomainError

if TYPE_CHECKING:
    from riso.contracts import CodingProposal, EvalReport
    from riso.contracts.eval import Split


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

    check = commands.add_parser(
        "check",
        help="check the committed data against the dictionaries, or with --customer one "
        "customer's knowledge health on the database",
    )
    check.add_argument(
        "--customer",
        metavar="IČO",
        help="report the knowledge health of this customer on the database of RISO_DB_URL",
    )
    check.add_argument(
        "--year", type=int, help="with --customer: the year (default: its newest parameters)"
    )

    schemas = commands.add_parser("export-schemas", help="write the contracts as JSON Schema")
    schemas.add_argument("--out", type=Path, default=paths.SCHEMAS_DIR)
    schemas.add_argument("--check", action="store_true", help="only report stale files")

    openapi = commands.add_parser(
        "export-openapi", help="write the API's OpenAPI document for the frontend client"
    )
    openapi.add_argument("--out", type=Path, default=None, help="default frontend/openapi.json")
    openapi.add_argument("--check", action="store_true", help="only report a stale file")

    commands.add_parser("reset", help="restore the runtime state from data/initial_state")

    serve = commands.add_parser("serve", help="run the API and the pages")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    code = commands.add_parser("code", help="propose the coding of invoices")
    code.add_argument(
        "invoices", type=Path, nargs="+", help="InvoiceDocument or dataset case JSON files"
    )
    code.add_argument("--json", action="store_true", help="print the full CodingProposal")

    evaluation = commands.add_parser("eval", help="evaluate the held-out set")
    evaluation.add_argument(
        "--split",
        choices=("heldout", "seed", "anchor"),
        default="heldout",
        help="cases to evaluate; seed and anchor cases are coded online (default heldout)",
    )
    evaluation.add_argument("--json", action="store_true", help="print the full EvalReport")
    evaluation.add_argument("--all", action="store_true", help="list every case, not only misses")
    evaluation.add_argument(
        "--strict", action="store_true", help="exit with 1 when a target of section 9 is missed"
    )
    evaluation.add_argument(
        "--source",
        choices=("files", "db"),
        default="files",
        help="where the lists, parameters and conventions come from: the committed files "
        "(default) or the database of RISO_DB_URL; the memory always comes from "
        "data/initial_state",
    )
    evaluation.add_argument(
        "--customer", metavar="IČO", help="the customer to evaluate (default: the dataset's one)"
    )

    migrate = commands.add_parser("migrate", help="upgrade the database to the newest schema")
    migrate.add_argument(
        "--revision", default="head", help="the Alembic revision to upgrade to (default head)"
    )

    seed = commands.add_parser(
        "seed", help="create the demo database: Boldog, a provider, a user per role (dev only)"
    )
    seed.add_argument("--reset", action="store_true", help="drop the database and the files first")

    worker = commands.add_parser("worker", help="run the background jobs worker")
    worker.add_argument("--once", action="store_true", help="run the jobs that are due, then exit")
    worker.add_argument(
        "--poll", type=float, default=1.0, help="seconds between looks for new jobs"
    )

    args = parser.parse_args(argv)
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "ingest": _ingest,
        "check": _check,
        "export-schemas": _export_schemas,
        "export-openapi": _export_openapi,
        "reset": _reset,
        "serve": _serve,
        "code": _code,
        "eval": _eval,
        "migrate": _migrate,
        "seed": _seed,
        "worker": _worker,
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
    if args.customer:
        return _health(args.customer, args.year)
    from riso.checks import run_checks

    results = run_checks()
    for result in results:
        print(f"{'FAIL' if result.errors else 'ok  '}  {result.name}")
        for error in result.errors:
            print(f"        {error}")
    failed = sum(1 for r in results if r.errors)
    print(f"{len(results) - failed} of {len(results)} checks passed")
    return 1 if failed else 0


def _health(ico: str, year: int | None) -> int:
    """The knowledge health report of a customer on the database (plan §6.5); exits with 1
    when it has errors."""
    from riso.api.composition import build_services
    from riso.codelists import HealthSeverity, knowledge_health
    from riso.shared.context import AllowAll, RequestContext
    from riso.shared.values import Ico

    services = build_services()
    try:
        with services.uow(immediate=False) as uow:
            customer = uow.customers.find_active_by_ico(Ico.parse(ico))
            years = uow.parameters.years(customer.id) if customer else []
        if customer is None:
            print(f"riso check: no active customer with IČO {ico}", file=sys.stderr)
            return 2
        chosen = year or (years[-1] if years else services.clock.now().year)
        ctx = RequestContext(request_id="riso-check", actor_id=None, policy=AllowAll())
        memory = services.supplier_state().memory(customer.id)
        findings = knowledge_health(ctx, services.uow(immediate=False), customer.id, chosen, memory)
    finally:
        services.close()
    print(f"{customer.name} ({ico}), {chosen}")
    for finding in findings:
        count = f" ×{finding.count}" if finding.count > 1 else ""
        print(f"  {finding.severity:<7}  {finding.message}{count}")
    errors = sum(f.severity is HealthSeverity.ERROR for f in findings)
    warnings = sum(f.severity is HealthSeverity.WARNING for f in findings)
    print(f"{errors} errors, {warnings} warnings, {len(findings) - errors - warnings} notes")
    return 1 if errors else 0


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


def _export_openapi(args: argparse.Namespace) -> int:
    from riso.api.openapi import OPENAPI_FILE, openapi_json

    out: Path = args.out or OPENAPI_FILE
    text = openapi_json()
    if args.check:
        current = out.read_text(encoding="utf-8") if out.is_file() else None
        if current != text:
            print(f"stale  {_shown(out)}; run `riso export-openapi`")
            return 1
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {_shown(out)}")
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
        "riso.api.app:create_served_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def _code(args: argparse.Namespace) -> int:
    """Codes each file with the current runtime state. For a dataset case it also says
    whether the codes match the expected ones, and exits with 1 when any does not."""
    import json

    from riso.contracts import DatasetCase, InvoiceDocument
    from riso.engine import code_invoice
    from riso.eval import compare
    from riso.knowledge import knowledge_for
    from riso.reference import LocalReferenceSource
    from riso.store import StateStore

    references, state = LocalReferenceSource(), StateStore()
    mismatches = 0
    for path in args.invoices:
        data = json.loads(path.read_text(encoding="utf-8"))
        case = DatasetCase.model_validate(data) if "expected" in data else None
        document = case.invoice if case else InvoiceDocument.model_validate(data)
        ico = "".join((document.customer.ico or "").split())
        try:
            entity = references.context(ico)
            proposal = code_invoice(
                document,
                entity=entity,
                bundle=references.bundle(ico, entity.reference_period),
                memory=state.supplier_memory(ico),
                counters=state.counters(ico),
                knowledge=knowledge_for(ico, entity.budget_year),
            )
        except LookupError as exc:
            print(f"riso code: {path}: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(proposal.model_dump_json(indent=2))
            continue
        print(_summary(proposal))
        if case is not None:
            expected = compare(proposal, case)
            print(
                f"  expected: {'matches' if expected is None else 'differs, expected ' + expected}"
            )
            mismatches += expected is not None
    return 1 if mismatches else 0


def _summary(proposal: "CodingProposal") -> str:
    """The proposal as the accountant would type it in, one line per budget line."""
    gross = proposal.invoice.gross
    document = proposal.document
    lines = [
        f"{proposal.invoice_id}  {proposal.supplier.name or '?'}  "
        f"{'—' if gross is None else f'{gross:.2f} €'}",
        f"  {document.number or '—'}, booking date {document.booking_date or '—'}",
    ]
    for post, budget in zip(proposal.posting, proposal.budget, strict=False):
        lines.append(
            f"  MD {post.md}  DAL {post.dal}  {budget.key}  {budget.amount:.2f}  "
            f"{post.text} | {budget.text}"
        )
    review = (
        "needs review: " + "; ".join(proposal.review_reasons)
        if proposal.needs_review
        else "no review needed"
    )
    lines.append(f"  confidence {proposal.confidence.overall:.2f}, {review}")
    return "\n".join(lines)


def _eval(args: argparse.Namespace) -> int:
    """Codes the split, prints the metrics and stores the report in var/<IČO>/, where
    GET /api/eval finds it."""
    from riso.eval import evaluate
    from riso.eval.report import render
    from riso.store import StateStore

    try:
        if args.source == "db":
            report = _evaluate_on_database(args.split, args.customer)
        else:
            report = evaluate(args.split, entity=args.customer)
    except (LookupError, ValueError, DomainError) as exc:
        print(f"riso eval: {exc}", file=sys.stderr)
        return 2
    if not report.cases:
        print(f"riso eval: no {args.split} cases", file=sys.stderr)
        return 2
    path = StateStore().save_eval(report)
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(render(report, all_cases=args.all))
        print(f"\nwrote {_shown(path)}")
    missed = [t for t in report.targets if not t.met]
    return 1 if args.strict and missed else 0


def _evaluate_on_database(split: "Split", customer: str | None) -> "EvalReport":
    from riso.api.adapters import DatabaseReferenceSource
    from riso.api.composition import build_services
    from riso.eval import evaluate
    from riso.shared.context import AllowAll, RequestContext

    services = build_services()
    try:
        ctx = RequestContext(request_id="riso-eval", actor_id=None, policy=AllowAll())
        source = DatabaseReferenceSource(
            lambda: services.uow(immediate=False), services.reference_data(), ctx
        )
        return evaluate(split, entity=customer, source=source, knowledge_of=source.knowledge)
    finally:
        services.close()


def _migrate(args: argparse.Namespace) -> int:
    """Upgrades the database of RISO_DB_URL (default var/riso.db)."""
    from riso.platform import Settings
    from riso.platform.migrations import current_revision, upgrade

    url = Settings().db_url
    before = current_revision(url)
    upgrade(url, args.revision)
    after = current_revision(url)
    if before == after:
        print(f"database at {after or 'base'}, nothing to do")
    else:
        print(f"migrated from {before or 'base'} to {after or 'base'}")
    return 0


def _seed(args: argparse.Namespace) -> int:
    """Seeds RISO_DB_URL. Passwords come from RISO_SEED_PASSWORD, or are generated and shown
    once. Refuses unless RISO_ENV is dev or test."""
    import os

    from riso.api.seed import SeedRefused, seed
    from riso.platform import Settings

    try:
        done = seed(
            Settings(), reset=args.reset, password=os.environ.get("RISO_SEED_PASSWORD") or None
        )
    except SeedRefused as exc:
        print(f"riso seed: {exc}", file=sys.stderr)
        return 2
    print("seeded:", ", ".join(done.customers), f"({done.invoices} invoices for Obec Boldog)")
    width = max(len(email) for _, email, _ in done.users.values())
    for key, (_, email, password) in done.users.items():
        shown = password if done.generated_passwords else "(RISO_SEED_PASSWORD)"
        print(f"  {key:<7} {email:<{width}}  {shown}")
    if done.generated_passwords:
        print("The passwords are shown only now; `riso seed --reset` makes new ones.")
    return 0


def _worker(args: argparse.Namespace) -> int:
    """Runs the jobs of RISO_DB_URL in the foreground, until Ctrl-C (or once)."""
    import threading

    from riso.api.composition import build_services

    services = build_services()
    try:
        worker = services.worker()
        if args.once:
            print(f"ran {worker.run_pending()} job(s)")
            return 0
        print(f"worker {worker.worker_id} running; Ctrl-C stops it")
        stop = threading.Event()
        try:
            while not stop.is_set():
                worker.run_pending()
                stop.wait(args.poll)
        except KeyboardInterrupt:
            print("stopped")
        return 0
    finally:
        services.close()


def _shown(path: Path) -> str:
    """The path relative to the working directory when it is below it."""
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
