"""The FastAPI app: the demo's JSON API and pages, and the phase 2 frame around them
(settings, the database, the jobs worker, the request ID, security headers, error mapping and
the SPA).

`create_app(Settings())` is the demo as it was: no database, the Alpine pages at `/`. `riso
serve` uses `create_served_app()`, which adds the database, the worker and the built SPA.
"""

import datetime as dt
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from riso import __version__, paths
from riso.api.admin import router as admin_router
from riso.api.composition import Services, build_services
from riso.api.errors import install_error_handlers
from riso.api.frontend import FrontendFiles
from riso.api.middleware import (
    CsrfCookieMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from riso.audit.api.routes import router as audit_router
from riso.contracts import (
    Alternative,
    CodeRequest,
    CodingProposal,
    EvalReport,
    Feedback,
    InvoiceDocument,
    ReferenceBundle,
)
from riso.contracts.base import Amount, BudgetKey, Ico
from riso.contracts.eval import Split
from riso.dataset import load_cases
from riso.engine import code_invoice, code_line
from riso.engine.s6_validate import check_coding
from riso.engine.s8_feedback import apply_feedback
from riso.eval import evaluate
from riso.identity.api.routes import router as identity_router
from riso.invoicing.api.routes import router as invoicing_router
from riso.knowledge import UnknownKnowledge, knowledge_for
from riso.platform.log import configure_logging
from riso.platform.migrations import current_revision, head_revision
from riso.platform.settings import Settings as PlatformSettings
from riso.reference import (
    LocalReferenceSource,
    ReferenceIndex,
    UnknownEntity,
    format_number,
    parse_number,
)
from riso.store import StateStore
from riso.tenancy.api.routes import router as tenancy_router

log = logging.getLogger(__name__)

ROUTERS = [identity_router, tenancy_router, invoicing_router, audit_router, admin_router]
"""The phase 2 routers. They are mounted with or without a database, so the OpenAPI document
and the permission matrix see the same routes; without one they answer 503."""

SPA_DIR = paths.WEB_DIR / "dist"
"""Where `pnpm build` in frontend/ puts the SPA. Git-ignored."""


@dataclass(frozen=True)
class Settings:
    bundles_dir: Path = paths.BUNDLES_DIR
    entities_dir: Path = paths.ENTITIES_DIR
    invoices_dir: Path = paths.INVOICES_DIR
    initial_state_dir: Path = paths.INITIAL_STATE_DIR
    var_dir: Path = field(default_factory=paths.var_dir)
    web_dir: Path = paths.WEB_DIR
    spa_dir: Path | None = None
    """The built SPA; None, or a folder without index.html, serves the demo pages at /."""
    platform: PlatformSettings | None = None
    """The database, files and jobs; None runs the demo without them."""
    run_worker: bool = True
    """Whether the lifespan runs the jobs worker in a thread (when there is a database)."""


class EntitySummary(BaseModel):
    ico: str
    name: str
    bundle_id: str
    periods: list[str]


class InvoiceListItem(BaseModel):
    """One row of the invoice picker."""

    id: str
    split: str
    supplier: str | None
    number: str | None
    issue_date: dt.date | None
    gross: Amount | None


class LineRequest(BaseModel):
    """Body of POST /api/line: the invoice, and a position the accountant picked."""

    invoice: InvoiceDocument
    entity: Ico | None = None
    budget_key: BudgetKey


class FeedbackReceipt(BaseModel):
    """What POST /api/feedback stored."""

    invoice_id: str
    action: str
    entity_ico: str
    document_number: str | None
    supplier_ico: str | None
    precedents: int  # the supplier's precedents in memory now; 0 without an IČO
    received_at: dt.datetime


class FeedbackItem(BaseModel):
    """One row of GET /api/feedback."""

    invoice_id: str
    action: str
    document_number: str | None
    received_at: dt.datetime | None


class SeriesCounter(BaseModel):
    """One row of GET /api/counters: a series' document numbers in one year."""

    series: str
    year: int
    last_used: str | None  # the highest number taken, e.g. FD/222/26; None before the first
    next: str  # what the counter fills in when the OCR could not read the handwritten number
    used: list[str]  # the numbers of this series and year already taken, lowest first


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    """The app. `services`, when given, replaces the ones built from `settings.platform`
    (tests pass a frozen clock and a fast password hasher)."""
    settings = settings or Settings()
    references = LocalReferenceSource(settings.bundles_dir, settings.entities_dir)
    state = StateStore(settings.var_dir, settings.initial_state_dir)
    if services is None and settings.platform is not None:
        services = build_services(settings.platform)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if services is not None:
            _require_migrated(services.settings.db_url)
            if settings.run_worker:
                services.worker_thread().start()
        try:
            yield
        finally:
            if services is not None:
                services.close()

    app = FastAPI(
        title="riso",
        version=__version__,
        summary="Invoice coding demo",
        lifespan=lifespan,
        # The operation ID is the route's unique name ("invoices.book"), the key of the
        # permission matrix and of the generated client's operations.
        generate_unique_id_function=lambda route: route.name,
    )
    app.state.services = services
    install_error_handlers(app)
    # Added last runs first: the request ID wraps everything, then the headers.
    if services is not None:
        app.add_middleware(
            CsrfCookieMiddleware,
            new_token=services.tokens.new_token,
            secure=services.settings.cookie_secure,
        )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)
    for router in ROUTERS:
        app.include_router(router)

    @app.get("/api/entities", name="legacy.entities")
    def entities() -> list[EntitySummary]:
        summaries = []
        for ico in references.entities():
            bundle = references.bundle(ico)
            summaries.append(
                EntitySummary(
                    ico=ico,
                    name=bundle.entity.name,
                    bundle_id=bundle.bundle_id,
                    periods=references.periods(ico),
                )
            )
        return summaries

    @app.get("/api/reference/{entity}", name="legacy.reference")
    def reference(entity: str, period: str | None = None) -> ReferenceBundle:
        try:
            return references.bundle(entity, period)
        except UnknownEntity as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/invoices", name="legacy.invoices")
    def invoices() -> list[InvoiceListItem]:
        return [
            InvoiceListItem(
                id=case.id,
                split=case.split,
                supplier=case.invoice.supplier.name,
                number=case.invoice.invoice.number,
                issue_date=case.invoice.invoice.issue_date,
                gross=case.invoice.totals.gross,
            )
            for case in load_cases(settings.invoices_dir)
        ]

    @app.get("/api/invoices/{invoice_id}", name="legacy.invoice")
    def invoice(invoice_id: str) -> InvoiceDocument:
        for case in load_cases(settings.invoices_dir):
            if case.id == invoice_id:
                return case.invoice
        raise HTTPException(404, f"no invoice {invoice_id}")

    def setting(ico: str) -> dict:
        """What the engine needs for an entity: its settings, bundle, knowledge and state."""
        try:
            entity = references.context(ico)
            bundle = references.bundle(ico, entity.reference_period)
            knowledge = knowledge_for(ico, entity.budget_year)
        except (UnknownEntity, UnknownKnowledge) as exc:
            raise HTTPException(404, str(exc)) from exc
        return {
            "entity": entity,
            "bundle": bundle,
            "knowledge": knowledge,
            "memory": state.supplier_memory(ico),
            "counters": state.counters(ico),
        }

    def customer(invoice: InvoiceDocument, entity: str | None) -> str:
        return entity or "".join((invoice.customer.ico or "").split())

    @app.post("/api/code", name="legacy.code")
    def code(request: CodeRequest) -> CodingProposal:
        return code_invoice(request.invoice, **setting(customer(request.invoice, request.entity)))

    @app.post("/api/line", name="legacy.line")
    def line(request: LineRequest) -> Alternative:
        """The whole line a position the accountant picked brings: MD, DAL, transfer, texts."""
        try:
            return code_line(
                request.invoice,
                request.budget_key,
                **setting(customer(request.invoice, request.entity)),
            )
        except KeyError as exc:
            raise HTTPException(404, f"{request.budget_key} is not in the budget") from exc

    @app.post("/api/feedback", name="legacy.feedback")
    def feedback(feedback: Feedback) -> FeedbackReceipt:
        """Stores the accountant's verdict: the coding becomes the supplier's newest precedent,
        its number is used up, and the feedback is logged. A corrected coding must pass the
        dictionary checks; whether its sum matches the invoice is the accountant's call."""
        ico = feedback.bundle_id.split("/")[0]
        period = feedback.bundle_id.split("/")[-1]
        try:
            bundle = references.bundle(ico, period)
        except UnknownEntity as exc:
            raise HTTPException(404, str(exc)) from exc
        index = ReferenceIndex(bundle)
        errors = check_coding(feedback.final, index).errors
        if errors:
            raise HTTPException(422, errors)
        memory, counters = apply_feedback(
            feedback, state.supplier_memory(ico), state.counters(ico), index
        )
        state.save_supplier_memory(memory)
        state.save_counters(counters)
        received = dt.datetime.now(dt.UTC).replace(microsecond=0)
        state.append_feedback(ico, feedback.model_copy(update={"received_at": received}))
        supplier_ico = feedback.supplier_ico or feedback.proposal.supplier.ico
        record = memory.find(supplier_ico) if supplier_ico else None
        return FeedbackReceipt(
            invoice_id=feedback.invoice_id,
            action=feedback.action,
            entity_ico=ico,
            document_number=feedback.final.document.number,
            supplier_ico=supplier_ico,
            precedents=len(record.precedents) if record else 0,
            received_at=received,
        )

    @app.get("/api/feedback", name="legacy.feedback_log")
    def feedback_log(entity: str = "00305863") -> list[FeedbackItem]:
        """The feedback stored since the last `riso reset`, oldest first."""
        return [
            FeedbackItem(
                invoice_id=item.invoice_id,
                action=item.action,
                document_number=item.final.document.number,
                received_at=item.received_at,
            )
            for item in state.feedback(entity)
        ]

    @app.get("/api/counters/{entity}", name="legacy.counters")
    def counters(entity: str) -> list[SeriesCounter]:
        """The document counters, invoice series first: the last number used, the one the
        counter would fill in next, and the numbers taken. Only feedback moves them."""
        try:
            context = references.context(entity)
            index = ReferenceIndex(references.bundle(entity, context.reference_period))
            counters = state.counters(entity)
        except UnknownEntity as exc:
            raise HTTPException(404, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, f"no counters for {entity}") from exc
        year = context.budget_year
        keys = [f"{context.default_series}/{year}", f"{context.canteen_series}/{year}"]
        rows = []
        for key in dict.fromkeys([*keys, *counters.last_used]):
            code, year_text = key.split("/")
            series = index.series.get(code)
            if series is None:
                continue
            series_year = int(year_text)
            taken = []
            for number in counters.used_numbers:
                parsed = parse_number(series.pattern, number)
                if parsed is not None and parsed.year == series_year % 100:
                    taken.append((parsed.sequence, number))
            last = counters.last_used.get(key, 0)
            rows.append(
                SeriesCounter(
                    series=code,
                    year=series_year,
                    last_used=format_number(series.pattern, last, series_year) if last else None,
                    next=format_number(series.pattern, last + 1, series_year),
                    used=[number for _, number in sorted(taken)],
                )
            )
        return rows

    @app.get("/api/eval", name="legacy.eval")
    def evaluation(
        entity: str = "00305863", split: Split = "heldout", refresh: bool = False
    ) -> EvalReport:
        """The latest report of `riso eval`; runs the evaluation when there is none yet, or
        when asked to refresh it."""
        report = None if refresh else state.eval_report(entity, split)
        if report is None:
            try:
                report = evaluate(
                    split,
                    entity=entity,
                    invoices_dir=settings.invoices_dir,
                    initial_dir=settings.initial_state_dir,
                    source=references,
                )
            except (UnknownEntity, UnknownKnowledge, FileNotFoundError) as exc:
                raise HTTPException(404, str(exc)) from exc
            state.save_eval(report)
        return report

    # Pages are the router's fallback: they never shadow an API route, and an unknown API
    # path gets a JSON 404 rather than a page.
    app.router.default = FrontendFiles(settings.web_dir, settings.spa_dir)
    return app


def create_served_app() -> FastAPI:
    """The app `riso serve` runs: the settings from the RISO_ variables, the database and the
    worker, and the built SPA when there is one."""
    configure_logging()
    platform = PlatformSettings()
    spa = SPA_DIR if (SPA_DIR / "index.html").is_file() else None
    if spa is None:
        log.warning("no built SPA in %s; serving the demo pages at /", SPA_DIR)
    return create_app(Settings(var_dir=platform.var_dir, spa_dir=spa, platform=platform))


def _require_migrated(url: str) -> None:
    current, head = current_revision(url), head_revision()
    if current != head:
        raise RuntimeError(
            f"the database is at {current or 'base'}, not {head}; run `riso migrate` first"
        )
