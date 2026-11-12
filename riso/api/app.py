"""The FastAPI app: the phase 2 API with its frame (settings, the database, the jobs worker,
the request ID, security headers, error mapping) and the built SPA, plus the two routes the
demo kept: `POST /api/code` (coding a posted invoice with the committed bundle and the initial
memory, for the evaluation and admin tools) and `GET /api/eval` (the latest `riso eval`
report, until Vyhodnotenie moves into the new UI in P2-M7). The demo's other routes and its
Alpine pages were removed in P2-M4-T10.

`create_app(Settings())` runs without a database (the phase 2 routes answer 503); `riso serve`
uses `create_served_app()`, which adds the database, the worker and the built SPA.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

from anyio import to_thread
from fastapi import Depends, FastAPI, HTTPException, Query

from riso import __version__, paths
from riso.api.admin import router as admin_router
from riso.api.composition import Services, build_services
from riso.api.deps import Caller, ServicesDep, check_csrf, platform_context
from riso.api.errors import install_error_handlers
from riso.api.frontend import FrontendFiles
from riso.api.limits import body_limit
from riso.api.middleware import (
    BodySizeLimitMiddleware,
    CsrfCookieMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from riso.audit.api.routes import router as audit_router
from riso.codelists.api.routes import router as codelists_router
from riso.contracts import (
    CodeRequest,
    CodingProposal,
    EvalReport,
)
from riso.contracts.eval import Split
from riso.engine import code_invoice
from riso.eval import evaluate
from riso.eval.files import initial_counters, initial_memory, load_report, save_report
from riso.exchange.api.routes import router as exchange_router
from riso.identity import Permission
from riso.identity.api.routes import router as identity_router
from riso.intake.api.routes import router as intake_router
from riso.invoicing.api.routes import router as invoicing_router
from riso.jobs.api.routes import router as jobs_router
from riso.knowledge import UnknownKnowledge, knowledge_for
from riso.platform.log import configure_logging
from riso.platform.migrations import current_revision, head_revision
from riso.platform.settings import Settings as PlatformSettings
from riso.reference import (
    LocalReferenceSource,
    UnknownEntity,
)
from riso.reporting.api.routes import router as reporting_router
from riso.tenancy.api.routes import router as tenancy_router

log = logging.getLogger(__name__)

ROUTERS = [
    identity_router,
    tenancy_router,
    codelists_router,
    exchange_router,
    invoicing_router,
    intake_router,
    reporting_router,
    audit_router,
    jobs_router,
    admin_router,
]
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
    spa_dir: Path | None = None
    """The built SPA; None, or a folder without index.html, serves a page saying how to build it."""
    platform: PlatformSettings | None = None
    """The database, files and jobs; None builds the app without them, for `riso
    export-openapi` and tests (the phase 2 routes answer 503). `riso serve` always has them."""
    run_worker: bool = True
    """Whether the lifespan runs the jobs worker in a thread (when there is a database)."""


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    """The app. `services`, when given, replaces the ones built from `settings.platform`
    (tests pass a frozen clock and a fast password hasher)."""
    settings = settings or Settings()
    references = LocalReferenceSource(settings.bundles_dir, settings.entities_dir)
    if services is None and settings.platform is not None:
        services = build_services(settings.platform)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if services is not None:
            # The synchronous routes run in anyio's thread pool, which is per event loop.
            to_thread.current_default_thread_limiter().total_tokens = (
                services.settings.request_threads
            )
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
        summary="Supplier invoices of Slovak municipalities",
        lifespan=lifespan,
        # The operation ID is the route's unique name ("invoices.book"), the key of the
        # permission matrix and of the generated client's operations.
        generate_unique_id_function=lambda route: route.name,
    )
    app.state.services = services
    install_error_handlers(app)
    # Added last runs first: the request ID wraps everything, then the headers, the CSRF
    # cookie and the body limit, so a 413 carries the headers and the request ID too.
    app.add_middleware(BodySizeLimitMiddleware, limit_for=body_limit)
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

    # The demo's evaluation tools, admins only since P2-M7 (plan §2 decision 67).
    Evaluator = Annotated[Caller, Depends(platform_context(Permission.EVALUATION_READ))]

    @app.post(
        "/api/admin/code",
        name="evaluation.code",
        tags=["admin"],
        dependencies=[Depends(check_csrf)],
    )
    def code(caller: Evaluator, services: ServicesDep, request: CodeRequest) -> CodingProposal:
        """The proposal for a posted invoice, coded with the committed bundle, the knowledge
        and the initial supplier memory and counters (`data/initial_state`), as `riso code`
        and the evaluation code it. Nothing is stored; customers' invoices are coded through
        `/api/customers/{id}/…`. (The services only make it a route like the others: the
        permission matrix test reaches every route through them.)"""
        del services
        ico = request.entity or "".join((request.invoice.customer.ico or "").split())
        try:
            entity = references.context(ico)
            return code_invoice(
                request.invoice,
                entity=entity,
                bundle=references.bundle(ico, entity.reference_period),
                memory=initial_memory(ico, settings.initial_state_dir),
                counters=initial_counters(ico, settings.initial_state_dir),
                knowledge=knowledge_for(ico, entity.budget_year),
            )
        except (UnknownEntity, UnknownKnowledge, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get(
        "/api/admin/eval",
        name="evaluation.get",
        tags=["admin"],
        dependencies=[Depends(check_csrf)],
    )
    def evaluation(
        caller: Evaluator,
        services: ServicesDep,
        # An IČO: it names the report's folder under var/ (P2-M8-T03).
        entity: Annotated[str, Query(pattern=r"^\d{8}$")] = "00305863",
        split: Split = "heldout",
        refresh: bool = False,
    ) -> EvalReport:
        """The latest report of `riso eval` (Vyhodnotenie); runs the evaluation when there is
        none yet, or when asked to refresh it."""
        var_dir = services.settings.var_dir
        report = None if refresh else load_report(entity, split, var_dir)
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
            save_report(report, var_dir)
        return report

    # Pages are the router's fallback: they never shadow an API route, and an unknown API
    # path gets a JSON 404 rather than a page.
    app.router.default = FrontendFiles(settings.spa_dir)
    return app


def create_served_app() -> FastAPI:
    """The app `riso serve` runs: the settings from the RISO_ variables, the database and the
    worker, and the built SPA when there is one."""
    configure_logging()
    platform = PlatformSettings()
    spa = SPA_DIR if (SPA_DIR / "index.html").is_file() else None
    if spa is None:
        log.warning("no built SPA in %s; run `pnpm build` in frontend/", SPA_DIR)
    return create_app(Settings(var_dir=platform.var_dir, spa_dir=spa, platform=platform))


def _require_migrated(url: str) -> None:
    current, head = current_revision(url), head_revision()
    if current != head:
        raise RuntimeError(
            f"the database is at {current or 'base'}, not {head}; run `riso migrate` first"
        )
