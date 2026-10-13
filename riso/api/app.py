"""The JSON API of plan section 8 and the static pages, served by one FastAPI app. The pages
call the same API a later integration would use."""

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from riso import __version__, paths
from riso.contracts import (
    CodeRequest,
    CodingProposal,
    EvalReport,
    Feedback,
    InvoiceDocument,
    ReferenceBundle,
)
from riso.contracts.base import Amount
from riso.contracts.eval import Split
from riso.dataset import load_cases
from riso.engine import code_invoice
from riso.eval import evaluate
from riso.knowledge import UnknownKnowledge, load_knowledge
from riso.reference import LocalReferenceSource, UnknownEntity
from riso.store import StateStore


@dataclass(frozen=True)
class Settings:
    bundles_dir: Path = paths.BUNDLES_DIR
    entities_dir: Path = paths.ENTITIES_DIR
    invoices_dir: Path = paths.INVOICES_DIR
    initial_state_dir: Path = paths.INITIAL_STATE_DIR
    var_dir: Path = field(default_factory=paths.var_dir)
    web_dir: Path = paths.WEB_DIR


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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    references = LocalReferenceSource(settings.bundles_dir, settings.entities_dir)
    state = StateStore(settings.var_dir, settings.initial_state_dir)
    app = FastAPI(title="riso", version=__version__, summary="Invoice coding demo")

    @app.get("/api/entities")
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

    @app.get("/api/reference/{entity}")
    def reference(entity: str, period: str | None = None) -> ReferenceBundle:
        try:
            return references.bundle(entity, period)
        except UnknownEntity as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/invoices")
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

    @app.get("/api/invoices/{invoice_id}")
    def invoice(invoice_id: str) -> InvoiceDocument:
        for case in load_cases(settings.invoices_dir):
            if case.id == invoice_id:
                return case.invoice
        raise HTTPException(404, f"no invoice {invoice_id}")

    @app.post("/api/code")
    def code(request: CodeRequest) -> CodingProposal:
        ico = request.entity or "".join((request.invoice.customer.ico or "").split())
        try:
            entity = references.context(ico)
            bundle = references.bundle(ico, entity.reference_period)
            knowledge = load_knowledge(entity.budget_year)
        except (UnknownEntity, UnknownKnowledge) as exc:
            raise HTTPException(404, str(exc)) from exc
        return code_invoice(
            request.invoice,
            entity=entity,
            bundle=bundle,
            memory=state.supplier_memory(ico),
            counters=state.counters(ico),
            knowledge=knowledge,
        )

    @app.post("/api/feedback", status_code=204)
    def feedback(feedback: Feedback) -> None:
        raise HTTPException(501, "The feedback store is built in M3")

    @app.get("/api/eval")
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

    app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
    return app
