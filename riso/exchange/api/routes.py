"""The exchange API: import runs, mapping templates and exports (plan §9.2, §7.4, §10.7).

A customer's imports live under `/api/customers/{customer_id}/imports`, the global lists'
under `/api/admin/imports`; both have the same steps:

1. `POST …/imports` uploads the file (multipart: `file`, `import_type`, `year`);
2. `GET …/imports/{id}/preview` reads it (sheet, header row, encoding and delimiter can be
   chosen) and suggests a mapping: the run's own, else a template chosen by the headers,
   else one from the header names;
3. `PUT …/imports/{id}/mapping` saves the options and the mapping;
4. `POST …/dry-run` and `POST …/apply` queue the jobs; the run's state and report show the
   outcome (`GET …/imports/{id}`); `POST …/cancel` gives up;
5. `POST …/imports/{id}/template` saves the mapping as a template.

`GET …/templates` lists the templates the owner may use; `PUT` and `DELETE` change or remove
one (built-in templates are read-only). Making a template needs the scope's permission,
which the use cases check: the route gate is using templates.
"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile
from fastapi.responses import Response

from riso.api.composition import Services
from riso.api.deps import Caller, ServicesDep, check_csrf, customer_context, platform_context
from riso.exchange.api.models import (
    ApplyIn,
    ExportIn,
    ExportPreviewOut,
    ExportRunOut,
    ExportRunPageOut,
    ImportPreviewOut,
    ImportRunOut,
    ImportRunPageOut,
    MappingIn,
    ReadOptionsIn,
    RunTemplateIn,
    TemplateIn,
    TemplateOut,
)
from riso.exchange.application.exports import (
    export_file,
    get_export,
    list_exports,
    preview_export,
    start_export,
)
from riso.exchange.application.imports import (
    MAX_PAGE,
    UploadImport,
    cancel_import,
    create_import,
    get_import,
    import_file,
    list_imports,
    preview_import,
    request_apply,
    set_mapping,
    start_dry_run,
)
from riso.exchange.application.templates import (
    SaveTemplate,
    TemplateChooser,
    delete_template,
    get_template,
    save_run_as_template,
    save_template,
    usable_templates,
)
from riso.exchange.domain.export import ExportFormat
from riso.exchange.domain.mapping import ImportType
from riso.exchange.domain.templates import TemplateScope
from riso.exchange.infrastructure.readers import MAX_FILE_BYTES
from riso.identity import Permission
from riso.shared.context import RequestContext
from riso.shared.errors import ValidationFailed

router = APIRouter(prefix="/api", dependencies=[Depends(check_csrf)], tags=["exchange"])

Editor = Annotated[Caller, Depends(customer_context(Permission.CODELISTS_EDIT))]
Reader = Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))]
TemplateUser = Annotated[Caller, Depends(customer_context(Permission.TEMPLATES_USE))]
GlobalEditor = Annotated[Caller, Depends(platform_context(Permission.GLOBAL_CODELISTS))]
GlobalTemplates = Annotated[Caller, Depends(platform_context(Permission.TEMPLATES_CREATE_GLOBAL))]
RunId = Annotated[str, Path(max_length=64)]
TemplateId = Annotated[str, Path(max_length=64)]


# The steps, for a customer (`owner` its ID) or the global lists (`owner` None) -----------


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValidationFailed.on(
            "file", f"larger than {MAX_FILE_BYTES // (1024 * 1024)} MB", "file_too_large"
        )
    return data


def _upload(
    ctx: RequestContext,
    services: Services,
    owner: str | None,
    import_type: ImportType,
    year: int,
    name: str,
    data: bytes,
) -> ImportRunOut:
    command = UploadImport(owner, import_type, year, name, data)
    return ImportRunOut.of(
        create_import(ctx, services.uow(), services.storage, services.reader, command)
    )


def _list(
    ctx: RequestContext, services: Services, owner: str | None, page: int, size: int
) -> ImportRunPageOut:
    runs, total = list_imports(ctx, services.uow(immediate=False), owner, page=page, size=size)
    return ImportRunPageOut(items=[ImportRunOut.of(r) for r in runs], total=total)


def _preview(
    ctx: RequestContext,
    services: Services,
    owner: str | None,
    run_id: str,
    options: ReadOptionsIn,
) -> ImportPreviewOut:
    given = options.options() if options.model_fields_set else None
    preview = preview_import(
        ctx,
        services.uow(immediate=False),
        services.storage,
        services.reader,
        owner,
        run_id,
        given,
        templates=TemplateChooser(services.uow(immediate=False), services.customers(), owner),
    )
    run = get_import(ctx, services.uow(immediate=False), owner, run_id)
    return ImportPreviewOut.of(preview, run.import_type)


def _map(
    ctx: RequestContext, services: Services, owner: str | None, run_id: str, body: MappingIn
) -> ImportRunOut:
    run = set_mapping(
        ctx,
        services.uow(),
        services.storage,
        services.reader,
        owner,
        run_id,
        body.options.options(),
        body.mapping,
        template_id=body.template_id,
    )
    return ImportRunOut.of(run)


def _file(ctx: RequestContext, services: Services, owner: str | None, run_id: str) -> Response:
    found = import_file(ctx, services.uow(immediate=False), services.storage, owner, run_id)
    return Response(
        found.data,
        media_type=found.media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{found.quoted_name}"},
    )


def _owner_of(services: Services, customer_id: str | None, scope: str) -> str | None:
    if scope == "customer":
        return customer_id
    if scope == "provider":
        provider = services.customers().provider_of(customer_id) if customer_id else None
        if provider is None:
            raise ValidationFailed.on("scope", "the customer has no provider", "no_provider")
        return provider
    return None


def _run_template(
    ctx: RequestContext,
    services: Services,
    owner: str | None,
    run_id: str,
    body: RunTemplateIn,
) -> TemplateOut:
    scope = TemplateScope(body.scope)
    view = save_run_as_template(
        ctx,
        services.uow(),
        services.storage,
        services.reader,
        owner,
        run_id,
        scope=scope,
        owner_id=_owner_of(services, owner, body.scope),
        name=body.name,
        template_id=body.template_id,
    )
    return TemplateOut.of(view)


def _templates(
    ctx: RequestContext, services: Services, owner: str | None, import_type: ImportType | None
) -> list[TemplateOut]:
    found = usable_templates(
        ctx, services.uow(immediate=False), services.customers(), owner, import_type
    )
    return [TemplateOut.of(t) for t in found]


def _update_template(
    ctx: RequestContext,
    services: Services,
    owner: str | None,
    template_id: str,
    body: TemplateIn,
) -> TemplateOut:
    found = get_template(
        ctx, services.uow(immediate=False), services.customers(), owner, template_id
    )
    command = SaveTemplate(
        found.scope, found.owner_id, body.name, body.signature, body.mapping, found.id
    )
    return TemplateOut.of(save_template(ctx, services.uow(), command))


def _delete_template(
    ctx: RequestContext, services: Services, owner: str | None, template_id: str
) -> None:
    found = get_template(
        ctx, services.uow(immediate=False), services.customers(), owner, template_id
    )
    delete_template(ctx, services.uow(), found.scope, found.owner_id, found.id)


Page = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=MAX_PAGE)]
UploadedFile = Annotated[UploadFile, File()]
TypeForm = Annotated[ImportType, Form()]
YearForm = Annotated[int, Form(ge=2000, le=2100)]


# A customer's imports ----------------------------------------------------------------------


@router.post("/customers/{customer_id}/imports", name="imports.upload", status_code=201)
async def customer_upload(
    caller: Editor,
    services: ServicesDep,
    customer_id: str,
    file: UploadedFile,
    import_type: TypeForm,
    year: YearForm,
) -> ImportRunOut:
    """Uploads a CSV, XLSX or XLS file and starts an import run."""
    data = await _read_upload(file)
    return _upload(caller.ctx, services, customer_id, import_type, year, file.filename or "", data)


@router.get("/customers/{customer_id}/imports", name="imports.list")
def customer_imports(
    caller: Reader, services: ServicesDep, customer_id: str, page: Page = 1, size: Size = 50
) -> ImportRunPageOut:
    """The customer's import runs, the newest first."""
    return _list(caller.ctx, services, customer_id, page, size)


@router.get("/customers/{customer_id}/imports/{run_id}", name="imports.get")
def customer_import(
    caller: Reader, services: ServicesDep, customer_id: str, run_id: RunId
) -> ImportRunOut:
    return ImportRunOut.of(
        get_import(caller.ctx, services.uow(immediate=False), customer_id, run_id)
    )


@router.get("/customers/{customer_id}/imports/{run_id}/file", name="imports.file")
def customer_import_file(
    caller: Reader, services: ServicesDep, customer_id: str, run_id: RunId
) -> Response:
    """The uploaded file, as it was uploaded."""
    return _file(caller.ctx, services, customer_id, run_id)


@router.get("/customers/{customer_id}/imports/{run_id}/preview", name="imports.preview")
def customer_preview(
    caller: Editor,
    services: ServicesDep,
    customer_id: str,
    run_id: RunId,
    options: Annotated[ReadOptionsIn, Query()],
) -> ImportPreviewOut:
    """The file read with the options (else the run's, else the readers' choices) and the
    suggested mapping."""
    return _preview(caller.ctx, services, customer_id, run_id, options)


@router.put("/customers/{customer_id}/imports/{run_id}/mapping", name="imports.map")
def customer_map(
    caller: Editor, services: ServicesDep, customer_id: str, run_id: RunId, body: MappingIn
) -> ImportRunOut:
    return _map(caller.ctx, services, customer_id, run_id, body)


@router.post(
    "/customers/{customer_id}/imports/{run_id}/dry-run", name="imports.dry_run", status_code=202
)
def customer_dry_run(
    caller: Editor, services: ServicesDep, customer_id: str, run_id: RunId
) -> ImportRunOut:
    """Queues the dry run; the run's report shows its outcome."""
    return ImportRunOut.of(start_dry_run(caller.ctx, services.uow(), customer_id, run_id))


@router.post(
    "/customers/{customer_id}/imports/{run_id}/apply", name="imports.apply", status_code=202
)
def customer_apply(
    caller: Editor, services: ServicesDep, customer_id: str, run_id: RunId, body: ApplyIn
) -> ImportRunOut:
    """Queues the apply. 409 for a run without a dry run, with hard errors, or with errors
    against the global lists that `confirm_errors` does not confirm."""
    run = request_apply(
        caller.ctx, services.uow(), customer_id, run_id, confirm_errors=body.confirm_errors
    )
    return ImportRunOut.of(run)


@router.post("/customers/{customer_id}/imports/{run_id}/cancel", name="imports.cancel")
def customer_cancel(
    caller: Editor, services: ServicesDep, customer_id: str, run_id: RunId
) -> ImportRunOut:
    return ImportRunOut.of(cancel_import(caller.ctx, services.uow(), customer_id, run_id))


@router.post(
    "/customers/{customer_id}/imports/{run_id}/template",
    name="imports.save_template",
    status_code=201,
)
def customer_run_template(
    caller: TemplateUser,
    services: ServicesDep,
    customer_id: str,
    run_id: RunId,
    body: RunTemplateIn,
) -> TemplateOut:
    """The run's mapping as a template of the customer, its provider, or global."""
    return _run_template(caller.ctx, services, customer_id, run_id, body)


@router.get("/customers/{customer_id}/templates", name="templates.list")
def customer_templates(
    caller: TemplateUser,
    services: ServicesDep,
    customer_id: str,
    import_type: ImportType | None = None,
) -> list[TemplateOut]:
    """The templates the customer may use: its own first, then its provider's, the global
    and the built-in ones."""
    return _templates(caller.ctx, services, customer_id, import_type)


@router.put("/customers/{customer_id}/templates/{template_id}", name="templates.update")
def customer_template_update(
    caller: TemplateUser,
    services: ServicesDep,
    customer_id: str,
    template_id: TemplateId,
    body: TemplateIn,
) -> TemplateOut:
    return _update_template(caller.ctx, services, customer_id, template_id, body)


@router.delete(
    "/customers/{customer_id}/templates/{template_id}", name="templates.delete", status_code=204
)
def customer_template_delete(
    caller: TemplateUser, services: ServicesDep, customer_id: str, template_id: TemplateId
) -> None:
    _delete_template(caller.ctx, services, customer_id, template_id)


# The global lists' imports ------------------------------------------------------------------


@router.post("/admin/imports", name="admin_imports.upload", status_code=201)
async def global_upload(
    caller: GlobalEditor,
    services: ServicesDep,
    file: UploadedFile,
    import_type: TypeForm,
    year: YearForm,
) -> ImportRunOut:
    """Uploads a global list's file (EK, COFOG, funding sources, the framework chart)."""
    data = await _read_upload(file)
    return _upload(caller.ctx, services, None, import_type, year, file.filename or "", data)


@router.get("/admin/imports", name="admin_imports.list")
def global_imports(
    caller: GlobalEditor, services: ServicesDep, page: Page = 1, size: Size = 50
) -> ImportRunPageOut:
    return _list(caller.ctx, services, None, page, size)


@router.get("/admin/imports/{run_id}", name="admin_imports.get")
def global_import(caller: GlobalEditor, services: ServicesDep, run_id: RunId) -> ImportRunOut:
    return ImportRunOut.of(get_import(caller.ctx, services.uow(immediate=False), None, run_id))


@router.get("/admin/imports/{run_id}/file", name="admin_imports.file")
def global_import_file(caller: GlobalEditor, services: ServicesDep, run_id: RunId) -> Response:
    return _file(caller.ctx, services, None, run_id)


@router.get("/admin/imports/{run_id}/preview", name="admin_imports.preview")
def global_preview(
    caller: GlobalEditor,
    services: ServicesDep,
    run_id: RunId,
    options: Annotated[ReadOptionsIn, Query()],
) -> ImportPreviewOut:
    return _preview(caller.ctx, services, None, run_id, options)


@router.put("/admin/imports/{run_id}/mapping", name="admin_imports.map")
def global_map(
    caller: GlobalEditor, services: ServicesDep, run_id: RunId, body: MappingIn
) -> ImportRunOut:
    return _map(caller.ctx, services, None, run_id, body)


@router.post("/admin/imports/{run_id}/dry-run", name="admin_imports.dry_run", status_code=202)
def global_dry_run(caller: GlobalEditor, services: ServicesDep, run_id: RunId) -> ImportRunOut:
    return ImportRunOut.of(start_dry_run(caller.ctx, services.uow(), None, run_id))


@router.post("/admin/imports/{run_id}/apply", name="admin_imports.apply", status_code=202)
def global_apply(
    caller: GlobalEditor, services: ServicesDep, run_id: RunId, body: ApplyIn
) -> ImportRunOut:
    run = request_apply(
        caller.ctx, services.uow(), None, run_id, confirm_errors=body.confirm_errors
    )
    return ImportRunOut.of(run)


@router.post("/admin/imports/{run_id}/cancel", name="admin_imports.cancel")
def global_cancel(caller: GlobalEditor, services: ServicesDep, run_id: RunId) -> ImportRunOut:
    return ImportRunOut.of(cancel_import(caller.ctx, services.uow(), None, run_id))


@router.post(
    "/admin/imports/{run_id}/template", name="admin_imports.save_template", status_code=201
)
def global_run_template(
    caller: GlobalTemplates, services: ServicesDep, run_id: RunId, body: RunTemplateIn
) -> TemplateOut:
    return _run_template(caller.ctx, services, None, run_id, body)


@router.get("/admin/templates", name="admin_templates.list")
def global_templates(
    caller: GlobalEditor, services: ServicesDep, import_type: ImportType | None = None
) -> list[TemplateOut]:
    """The global and built-in templates of the global lists."""
    return _templates(caller.ctx, services, None, import_type)


@router.put("/admin/templates/{template_id}", name="admin_templates.update")
def global_template_update(
    caller: GlobalTemplates, services: ServicesDep, template_id: TemplateId, body: TemplateIn
) -> TemplateOut:
    return _update_template(caller.ctx, services, None, template_id, body)


@router.delete("/admin/templates/{template_id}", name="admin_templates.delete", status_code=204)
def global_template_delete(
    caller: GlobalTemplates, services: ServicesDep, template_id: TemplateId
) -> None:
    _delete_template(caller.ctx, services, None, template_id)


Processor = Annotated[Caller, Depends(customer_context(Permission.INVOICES_PROCESS))]


@router.post("/customers/{customer_id}/exports/preview", name="exports.preview")
def export_preview(
    caller: Processor, services: ServicesDep, customer_id: str, body: ExportIn
) -> ExportPreviewOut:
    """What an export of the selection or filter would hold, for the dialog: the booked,
    exported and paid invoices, how many were exported before, how many are skipped."""
    found = preview_export(caller.ctx, services.uow(immediate=False), customer_id, body.scope())
    return ExportPreviewOut(invoices=found.invoices, again=found.again, skipped=found.skipped)


@router.post("/customers/{customer_id}/exports", name="exports.start", status_code=202)
def export_start(
    caller: Processor, services: ServicesDep, customer_id: str, body: ExportIn
) -> ExportRunOut:
    """Starts an export (plan §7.4): its `export_build` job writes the CSV or XLSX of the
    booked invoices, keeps it in storage and records the export on each invoice. Follow the
    run (`GET …/exports/{id}`) or the job. 422 when no booked invoice is chosen."""
    view = start_export(
        caller.ctx, services.uow(), customer_id, ExportFormat(body.format), body.scope()
    )
    return ExportRunOut.of(view)


@router.get("/customers/{customer_id}/exports", name="exports.list")
def export_runs(
    caller: Reader,
    services: ServicesDep,
    customer_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ExportRunPageOut:
    """The customer's exports, the newest first (Importy a exporty)."""
    found = list_exports(
        caller.ctx, services.uow(immediate=False), customer_id, page=page, size=size
    )
    return ExportRunPageOut(items=[ExportRunOut.of(r) for r in found.items], total=found.total)


@router.get("/customers/{customer_id}/exports/{run_id}", name="exports.get")
def export_run(
    caller: Reader, services: ServicesDep, customer_id: str, run_id: RunId
) -> ExportRunOut:
    return ExportRunOut.of(
        get_export(caller.ctx, services.uow(immediate=False), customer_id, run_id)
    )


@router.get("/customers/{customer_id}/exports/{run_id}/file", name="exports.file")
def export_run_file(
    caller: Reader, services: ServicesDep, customer_id: str, run_id: RunId
) -> Response:
    """The export's file, as written; 404 before the job wrote it."""
    found = export_file(
        caller.ctx, services.uow(immediate=False), services.storage, customer_id, run_id
    )
    return Response(
        found.data,
        media_type=found.media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(found.name)}"},
    )
