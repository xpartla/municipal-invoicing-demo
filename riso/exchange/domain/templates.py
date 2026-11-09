"""Mapping templates (plan §9.2 step 5): a saved mapping with a name, the header signature of
the files it was made for, and a scope saying who may use it.

| Scope | Owner | Seen by | Made by |
|---|---|---|---|
| builtin | none | everyone | the code (`BUILTIN`): TOPSET's four exports, the global lists' CSV |
| global | none | everyone | admins |
| provider | a service provider | its staff and its customers | the provider's staff |
| customer | a customer | that customer | the customer's users |

A file gets the template whose signature equals its own, for the import's type, preferring
the narrowest scope (customer, provider, global, built-in) and then the newest.

The built-in TOPSET templates read the exports as `riso ingest` does (riso/ingest/build.py):
codes trimmed and zero-padded to their widths, the account type from TOPSET's Slovak names,
the zdroj as written, duplicate accounts kept first and duplicate budget keys merged, and
the chart's title row giving the period and the IČO.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from riso.exchange.domain.mapping import (
    ColumnMapping,
    Fact,
    FieldSource,
    ImportType,
    Trim,
    ZeroPad,
)
from riso.exchange.domain.suggestions import header_signature
from riso.shared.errors import InvalidState, ValidationFailed
from riso.shared.events import DomainEvent

MAX_NAME = 120


class TemplateScope(StrEnum):
    BUILTIN = "builtin"
    GLOBAL = "global"
    PROVIDER = "provider"
    CUSTOMER = "customer"


PRIORITY = {
    TemplateScope.CUSTOMER: 0,
    TemplateScope.PROVIDER: 1,
    TemplateScope.GLOBAL: 2,
    TemplateScope.BUILTIN: 3,
}


@dataclass(frozen=True, slots=True)
class TemplateSaved(DomainEvent):
    template_id: str
    scope: TemplateScope
    owner_id: str | None
    import_type: ImportType


def _name(name: str) -> str:
    text = " ".join(name.split())
    if not text:
        raise ValidationFailed.on("name", "required", "missing")
    if len(text) > MAX_NAME:
        raise ValidationFailed.on("name", f"at most {MAX_NAME} characters", "string_too_long")
    return text


@dataclass(slots=True)
class MappingTemplate:
    id: str
    scope: TemplateScope
    owner_id: str | None
    """The customer or the provider; None for a global or built-in template."""
    name: str
    signature: str
    mapping: ColumnMapping
    created_at: datetime
    created_by: str | None
    updated_at: datetime
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    @property
    def import_type(self) -> ImportType:
        return self.mapping.import_type

    @property
    def builtin(self) -> bool:
        return self.scope is TemplateScope.BUILTIN

    @classmethod
    def create(
        cls,
        template_id: str,
        scope: TemplateScope,
        owner_id: str | None,
        name: str,
        signature: str,
        mapping: ColumnMapping,
        *,
        at: datetime,
        actor: str | None,
    ) -> "MappingTemplate":
        if scope is TemplateScope.BUILTIN:
            raise InvalidState("built-in templates come with the code")
        owned = scope in (TemplateScope.PROVIDER, TemplateScope.CUSTOMER)
        if owned != (owner_id is not None):
            raise InvalidState(f"a {scope} template {'needs' if owned else 'has no'} owner")
        if mapping.import_type.is_global and scope is not TemplateScope.GLOBAL:
            raise InvalidState("templates for the global lists are global")
        template = cls(
            template_id,
            scope,
            owner_id,
            _name(name),
            signature,
            mapping,
            at,
            actor,
            at,
        )
        template.events.append(TemplateSaved(template_id, scope, owner_id, mapping.import_type))
        return template

    def update(self, name: str, signature: str, mapping: ColumnMapping, at: datetime) -> None:
        if self.builtin:
            raise InvalidState("a built-in template cannot change")
        if mapping.import_type is not self.import_type:
            raise InvalidState(f"a {self.import_type} template takes a {self.import_type} mapping")
        self.name, self.signature, self.mapping, self.updated_at = (
            _name(name),
            signature,
            mapping,
            at,
        )
        self.events.append(TemplateSaved(self.id, self.scope, self.owner_id, self.import_type))


def choose_template(
    templates: Iterable[MappingTemplate], import_type: ImportType, signature: str
) -> MappingTemplate | None:
    """The template for a file of `signature` imported as `import_type`: the narrowest
    scope, then the newest."""
    matching = [t for t in templates if t.import_type is import_type and t.signature == signature]
    if not matching:
        return None
    return min(matching, key=lambda t: (PRIORITY[t.scope], -t.updated_at.timestamp(), t.id))


# Built-in templates -----------------------------------------------------------------------

BUILTIN_AT = datetime(2026, 11, 9, tzinfo=UTC)
TOPSET_CHART_HEADER = ("SU", "AU", "Typ účtu", "Zarad. SÚV", "Zarad. VZaS", "Činnosť", "Popis")
TOPSET_BUDGET_HEADER = ("Kód", "Zdroj", "Oddiel", "Trieda", "Analytika", "Popis")
TOPSET_SERIES_HEADER = ("Evidenčné číslo", "Vzor dokladu", "Popis", "Bankový účet")
GLOBAL_HEADER = ("code", "name")

TRIM = (Trim(),)


def _pad(width: int) -> tuple[Trim | ZeroPad, ...]:
    return (Trim(), ZeroPad(width=width))


def _builtin(
    key: str, name: str, header: tuple[str, ...], mapping: ColumnMapping
) -> MappingTemplate:
    return MappingTemplate(
        f"builtin:{key}",
        TemplateScope.BUILTIN,
        None,
        name,
        header_signature(header),
        mapping,
        BUILTIN_AT,
        None,
        BUILTIN_AT,
    )


def _budget(import_type: ImportType) -> ColumnMapping:
    return ColumnMapping(
        import_type=import_type,
        fields={
            "ek": FieldSource(column="Kód", transforms=_pad(6)),
            "zdroj": FieldSource(column="Zdroj", transforms=TRIM),
            "oddiel": FieldSource(column="Oddiel", transforms=_pad(2)),
            "trieda": FieldSource(column="Trieda", transforms=_pad(3)),
            "analytika": FieldSource(column="Analytika", transforms=_pad(3)),
            "description": FieldSource(column="Popis", transforms=TRIM),
        },
    )


def _global(import_type: ImportType) -> ColumnMapping:
    return ColumnMapping(
        import_type=import_type,
        fields={
            "code": FieldSource(column="code", transforms=TRIM),
            "name": FieldSource(column="name", transforms=TRIM),
        },
    )


TOPSET_CHART_FACTS = (
    Fact(name="ico", row=1, pattern=r"IČO:\s*(?P<ico>\d{6,8})"),
    Fact(name="period", row=1, pattern=r"Obdobie:\s*(?P<month>\d{1,2})\.\s*(?P<year>\d{4})"),
)

_GLOBAL_NAMES = {
    ImportType.EK: "Ekonomická klasifikácia (CSV code, name)",
    ImportType.COFOG: "Funkčná klasifikácia COFOG (CSV code, name)",
    ImportType.FUNDING_SOURCES: "Zdroje financovania (CSV code, name)",
    ImportType.FRAMEWORK_ACCOUNTS: "Rámcová účtová osnova (CSV code, name)",
}

BUILTIN: dict[str, MappingTemplate] = {
    t.id: t
    for t in (
        _builtin(
            "topset-chart",
            "TOPSET – Účtový rozvrh",
            TOPSET_CHART_HEADER,
            ColumnMapping(
                import_type=ImportType.ACCOUNTS,
                fields={
                    "su": FieldSource(column="SU", transforms=_pad(3)),
                    "au": FieldSource(column="AU", transforms=_pad(3)),
                    "type": FieldSource(column="Typ účtu", transforms=TRIM),
                    "activity": FieldSource(column="Činnosť", transforms=TRIM),
                    "description": FieldSource(column="Popis", transforms=TRIM),
                },
                facts=TOPSET_CHART_FACTS,
            ),
        ),
        _builtin(
            "topset-expense",
            "TOPSET – Výkaz výdavkov",
            TOPSET_BUDGET_HEADER,
            _budget(ImportType.BUDGET_EXPENSE),
        ),
        _builtin(
            "topset-income",
            "TOPSET – Výkaz príjmov",
            TOPSET_BUDGET_HEADER,
            _budget(ImportType.BUDGET_INCOME),
        ),
        _builtin(
            "topset-series",
            "TOPSET – Číselné rady dokladov",
            TOPSET_SERIES_HEADER,
            ColumnMapping(
                import_type=ImportType.DOCUMENT_SERIES,
                fields={
                    "series_id": FieldSource(column="Evidenčné číslo", transforms=TRIM),
                    "pattern": FieldSource(column="Vzor dokladu", transforms=TRIM),
                    "description": FieldSource(column="Popis", transforms=TRIM),
                    "bank_account": FieldSource(column="Bankový účet", transforms=TRIM),
                },
            ),
        ),
        *(
            _builtin(f"global-{t.value}", name, GLOBAL_HEADER, _global(t))
            for t, name in _GLOBAL_NAMES.items()
        ),
    )
}
"""The built-in templates by ID (`builtin:topset-chart`, `builtin:global-ek`, …)."""


def builtin_for(import_type: ImportType) -> list[MappingTemplate]:
    return [t for t in BUILTIN.values() if t.import_type is import_type]
