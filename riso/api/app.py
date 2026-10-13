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
from riso.knowledge import UnknownKnowledge, load_knowledge
from riso.reference import LocalReferenceSource, ReferenceIndex, UnknownEntity
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

    def setting(ico: str) -> dict:
        """What the engine needs for an entity: its settings, bundle, knowledge and state."""
        try:
            entity = references.context(ico)
            bundle = references.bundle(ico, entity.reference_period)
            knowledge = load_knowledge(entity.budget_year)
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

    @app.post("/api/code")
    def code(request: CodeRequest) -> CodingProposal:
        return code_invoice(request.invoice, **setting(customer(request.invoice, request.entity)))

    @app.post("/api/line")
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

    @app.post("/api/feedback")
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

    @app.get("/api/feedback")
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
