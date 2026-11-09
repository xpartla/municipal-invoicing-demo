"""One import run from file to new version, synchronously: the use cases the wizard calls,
with the worker run in between. `riso seed` loads the global lists this way, and the local
test of P2-M3's exit criterion imports TOPSET's exports with it."""

from riso.api.composition import Services
from riso.exchange.application.imports import (
    ImportRunView,
    UploadImport,
    create_import,
    get_import,
    preview_import,
    request_apply,
    set_mapping,
    start_dry_run,
)
from riso.exchange.application.templates import TemplateChooser
from riso.exchange.domain.mapping import ImportType
from riso.exchange.domain.run import RunState
from riso.exchange.domain.table import ReadOptions
from riso.exchange.domain.templates import MappingTemplate
from riso.shared.context import RequestContext


def run_import(
    services: Services,
    ctx: RequestContext,
    customer_id: str | None,
    import_type: ImportType,
    year: int,
    filename: str,
    data: bytes,
    *,
    template: MappingTemplate | None = None,
    confirm_errors: bool = False,
) -> ImportRunView:
    """Uploads, maps (with `template`, else the template the file's headers choose, else
    the suggestion), runs the dry run and, when it allows, applies. Returns the run as it
    ended: `applied`, or `dry_run_failed` with its report."""
    run = create_import(
        ctx,
        services.uow(),
        services.storage,
        services.reader,
        UploadImport(customer_id, import_type, year, filename, data),
    )
    preview = preview_import(
        ctx,
        services.uow(),
        services.storage,
        services.reader,
        customer_id,
        run.id,
        templates=TemplateChooser(services.uow(immediate=False), services.customers(), customer_id),
    )
    mapping = template.mapping if template is not None else preview.suggestion
    template_id = template.id if template is not None else preview.template_id
    options = ReadOptions(
        sheet=preview.sheet,
        header_row=preview.header_row,
        encoding=preview.encoding,
        delimiter=preview.delimiter,
    )
    set_mapping(
        ctx,
        services.uow(),
        services.storage,
        services.reader,
        customer_id,
        run.id,
        options,
        mapping,
        template_id=template_id,
    )
    start_dry_run(ctx, services.uow(), customer_id, run.id)
    worker = services.worker()
    worker.run_pending()
    run = get_import(ctx, services.uow(), customer_id, run.id)
    if not run.can_apply or (run.state is RunState.DRY_RUN_FAILED and not confirm_errors):
        return run
    request_apply(ctx, services.uow(), customer_id, run.id, confirm_errors=confirm_errors)
    worker.run_pending()
    return get_import(ctx, services.uow(), customer_id, run.id)


def first_error(run: ImportRunView) -> str:
    """The run's first error as `<file> row <n>: <message>`, for a command's output."""
    if run.report is None or not run.report.errors:
        return f"{run.file_name}: {run.state}"
    error = run.report.errors[0]
    where = f" row {error.rows[0]}" if error.rows else ""
    return f"{run.file_name}{where}: {error.message}"
