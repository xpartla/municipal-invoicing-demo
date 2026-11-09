"""Mapping templates (plan §9.2 step 5, §5.2): listing the templates a customer may use,
saving and deleting them per scope, saving an import's mapping as one, and choosing one for
a file by its header signature.

Permissions (plan §5.2): using templates needs `templates.use` in the customer; making them
needs `templates.create_customer` in the customer, `templates.create_provider` in the
provider, or `templates.create_global` on the platform. Built-in templates are read-only.
"""

from dataclasses import dataclass
from datetime import datetime

from riso.exchange.application.ports import CustomerDirectory, TableReader
from riso.exchange.application.uow import ExchangeUnitOfWork
from riso.exchange.domain.mapping import ColumnMapping, ImportType
from riso.exchange.domain.suggestions import header_signature, resolve_columns
from riso.exchange.domain.table import Workbook
from riso.exchange.domain.templates import (
    BUILTIN,
    MappingTemplate,
    TemplateScope,
    choose_template,
)
from riso.identity import Permission
from riso.shared.context import RequestContext
from riso.shared.errors import InvalidState, NotFound, ValidationFailed
from riso.shared.ports import FileStorage


@dataclass(frozen=True, slots=True)
class TemplateView:
    id: str
    scope: TemplateScope
    owner_id: str | None
    name: str
    import_type: ImportType
    signature: str
    mapping: ColumnMapping
    created_at: datetime
    created_by: str | None
    updated_at: datetime

    @property
    def builtin(self) -> bool:
        return self.scope is TemplateScope.BUILTIN

    @classmethod
    def of(cls, template: MappingTemplate) -> "TemplateView":
        return cls(
            id=template.id,
            scope=template.scope,
            owner_id=template.owner_id,
            name=template.name,
            import_type=template.import_type,
            signature=template.signature,
            mapping=template.mapping,
            created_at=template.created_at,
            created_by=template.created_by,
            updated_at=template.updated_at,
        )


def _require_create(ctx: RequestContext, scope: TemplateScope, owner_id: str | None) -> None:
    if scope is TemplateScope.CUSTOMER:
        ctx.require(Permission.TEMPLATES_CREATE_CUSTOMER, owner_id)
    elif scope is TemplateScope.PROVIDER:
        ctx.require(Permission.TEMPLATES_CREATE_PROVIDER, provider_id=owner_id)
    elif scope is TemplateScope.GLOBAL:
        ctx.require(Permission.TEMPLATES_CREATE_GLOBAL)
    else:
        raise InvalidState("built-in templates come with the code")


def _visible(
    uow: ExchangeUnitOfWork, customers: CustomerDirectory, customer_id: str | None
) -> list[MappingTemplate]:
    """What a customer's import (None: a global list's import) may use."""
    found = list(BUILTIN.values()) + uow.templates.owned(TemplateScope.GLOBAL, None)
    if customer_id is not None:
        provider_id = customers.provider_of(customer_id)
        if provider_id is not None:
            found += uow.templates.owned(TemplateScope.PROVIDER, provider_id)
        found += uow.templates.owned(TemplateScope.CUSTOMER, customer_id)
    return found


def _require_use(ctx: RequestContext, customer_id: str | None) -> None:
    if customer_id is None:
        ctx.require(Permission.GLOBAL_CODELISTS)
    else:
        ctx.require(Permission.TEMPLATES_USE, customer_id)


def usable_templates(
    ctx: RequestContext,
    uow: ExchangeUnitOfWork,
    customers: CustomerDirectory,
    customer_id: str | None,
    import_type: ImportType | None = None,
) -> list[TemplateView]:
    """The templates an import in the customer (None: of a global list) may use, the
    narrowest scope first, by name."""
    _require_use(ctx, customer_id)
    with uow:
        found = _visible(uow, customers, customer_id)
    if import_type is not None:
        found = [t for t in found if t.import_type is import_type]
    if customer_id is None:
        found = [t for t in found if t.import_type.is_global]
    order = {TemplateScope.CUSTOMER: 0, TemplateScope.PROVIDER: 1}
    found.sort(key=lambda t: (order.get(t.scope, 2), t.builtin, t.name.casefold()))
    return [TemplateView.of(t) for t in found]


def owned_templates(
    ctx: RequestContext, uow: ExchangeUnitOfWork, scope: TemplateScope, owner_id: str | None
) -> list[TemplateView]:
    """The templates of one scope and owner, for whoever may make them."""
    _require_create(ctx, scope, owner_id)
    with uow:
        return [TemplateView.of(t) for t in uow.templates.owned(scope, owner_id)]


@dataclass(frozen=True, slots=True)
class SaveTemplate:
    scope: TemplateScope
    owner_id: str | None
    name: str
    signature: str
    mapping: ColumnMapping
    template_id: str | None = None
    """An existing template of the scope and owner to replace; None for a new one."""


def save_template(ctx: RequestContext, uow: ExchangeUnitOfWork, cmd: SaveTemplate) -> TemplateView:
    _require_create(ctx, cmd.scope, cmd.owner_id)
    with uow:
        now = uow.clock.now()
        if cmd.template_id is None:
            template = MappingTemplate.create(
                uow.ids.new(),
                cmd.scope,
                cmd.owner_id,
                cmd.name,
                cmd.signature,
                cmd.mapping,
                at=now,
                actor=ctx.actor_id,
            )
            uow.templates.add(template)
            action = "templates.created"
        else:
            template = uow.templates.get(cmd.scope, cmd.owner_id, cmd.template_id)
            template.update(cmd.name, cmd.signature, cmd.mapping, now)
            uow.templates.save(template)
            action = "templates.updated"
        uow.audit.record(
            ctx,
            action,
            target_type="mapping_template",
            target_id=template.id,
            customer_id=cmd.owner_id if cmd.scope is TemplateScope.CUSTOMER else None,
            details={
                "scope": cmd.scope.value,
                "owner_id": cmd.owner_id,
                "import_type": template.import_type.value,
            },
        )
        uow.commit()
    return TemplateView.of(template)


def delete_template(
    ctx: RequestContext,
    uow: ExchangeUnitOfWork,
    scope: TemplateScope,
    owner_id: str | None,
    template_id: str,
) -> None:
    _require_create(ctx, scope, owner_id)
    with uow:
        template = uow.templates.get(scope, owner_id, template_id)
        uow.templates.delete(template)
        uow.audit.record(
            ctx,
            "templates.deleted",
            target_type="mapping_template",
            target_id=template.id,
            customer_id=owner_id if scope is TemplateScope.CUSTOMER else None,
            details={"scope": scope.value, "owner_id": owner_id},
        )
        uow.commit()


def save_run_as_template(
    ctx: RequestContext,
    uow: ExchangeUnitOfWork,
    storage: FileStorage,
    reader: TableReader,
    customer_id: str | None,
    run_id: str,
    *,
    scope: TemplateScope,
    owner_id: str | None,
    name: str,
    template_id: str | None = None,
) -> TemplateView:
    """The run's mapping as a template, signed with the headers of the run's file."""
    if customer_id is None:
        ctx.require(Permission.GLOBAL_CODELISTS)
    else:
        ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        run = uow.imports.get(customer_id, run_id)
    if run.mapping is None:
        raise ValidationFailed.on("mapping", "the import has no mapping yet", "missing")
    with storage.open(run.file.storage_key) as handle:
        workbook = reader.read(handle.read(), run.options)
    return save_template(
        ctx,
        uow,
        SaveTemplate(
            scope,
            owner_id,
            name,
            header_signature(workbook.table.headers),
            run.mapping,
            template_id,
        ),
    )


@dataclass(frozen=True, slots=True)
class ChosenTemplate:
    id: str
    name: str
    mapping: ColumnMapping
    """Resolved against the file's columns."""


class TemplateChooser:
    """Picks the template for a file in a unit of work of its own: `preview_import`'s
    `templates` hook."""

    def __init__(
        self, uow: ExchangeUnitOfWork, customers: CustomerDirectory, customer_id: str | None
    ) -> None:
        self._uow = uow
        self._customers = customers
        self._customer_id = customer_id

    def __call__(self, workbook: Workbook, import_type: ImportType) -> ChosenTemplate | None:
        with self._uow:
            found = _visible(self._uow, self._customers, self._customer_id)
        template = choose_template(found, import_type, header_signature(workbook.table.headers))
        if template is None:
            return None
        mapping = resolve_columns(template.mapping, workbook.table)
        try:
            mapping.check_against(workbook.table)
        except ValidationFailed:
            return None
        return ChosenTemplate(template.id, template.name, mapping)


def get_template(
    ctx: RequestContext,
    uow: ExchangeUnitOfWork,
    customers: CustomerDirectory,
    customer_id: str | None,
    template_id: str,
) -> TemplateView:
    """A template the customer's imports may use."""
    _require_use(ctx, customer_id)
    with uow:
        for template in _visible(uow, customers, customer_id):
            if template.id == template_id:
                return TemplateView.of(template)
    raise NotFound(f"no template {template_id}")
