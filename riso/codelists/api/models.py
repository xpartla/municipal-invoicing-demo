"""Request and response models of the codelists API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from riso.codelists.application import ConventionsView
from riso.codelists.application.lists import (
    ChecklistYear,
    DiffView,
    EntryPage,
    EntryView,
    ListsOverview,
    ListSummary,
    VersionView,
)
from riso.codelists.domain import (
    HealthCode,
    HealthFinding,
    HealthSeverity,
    ListKind,
    VersionOrigin,
    VersionStatus,
)


class HealthFindingOut(BaseModel):
    code: HealthCode
    severity: HealthSeverity
    subject: str
    where: str | None
    kind: ListKind | None
    count: int
    message: str

    @classmethod
    def of(cls, finding: HealthFinding) -> "HealthFindingOut":
        return cls(
            code=finding.code,
            severity=finding.severity,
            subject=finding.subject,
            where=finding.where,
            kind=finding.kind,
            count=finding.count,
            message=finding.message,
        )


class HealthReportOut(BaseModel):
    year: int
    errors: int
    warnings: int
    findings: list[HealthFindingOut]

    @classmethod
    def of(cls, year: int, findings: list[HealthFinding]) -> "HealthReportOut":
        return cls(
            year=year,
            errors=sum(f.severity is HealthSeverity.ERROR for f in findings),
            warnings=sum(f.severity is HealthSeverity.WARNING for f in findings),
            findings=[HealthFindingOut.of(f) for f in findings],
        )


class VersionOut(BaseModel):
    id: str
    kind: ListKind
    year: int
    number: int
    status: VersionStatus
    origin: VersionOrigin
    created_at: datetime
    created_by: str | None
    entry_count: int
    period: str | None
    note: str | None

    @classmethod
    def of(cls, view: VersionView) -> "VersionOut":
        return cls(**{name: getattr(view, name) for name in cls.model_fields})


class EntryOut(BaseModel):
    key: str
    active: bool
    values: dict[str, Any] = Field(description="The entry's fields; amounts are numbers")

    @classmethod
    def of(cls, view: EntryView) -> "EntryOut":
        return cls(key=view.key, active=view.active, values=view.values)


class EntryPageOut(BaseModel):
    version: VersionOut
    items: list[EntryOut]
    total: int

    @classmethod
    def of(cls, page: EntryPage) -> "EntryPageOut":
        return cls(
            version=VersionOut.of(page.version),
            items=[EntryOut.of(e) for e in page.items],
            total=page.total,
        )


class ListSummaryOut(BaseModel):
    kind: ListKind
    fields: list[str] = Field(description="The fields an entry of the list has")
    version: VersionOut | None

    @classmethod
    def of(cls, summary: ListSummary) -> "ListSummaryOut":
        return cls(
            kind=summary.kind,
            fields=list(summary.fields),
            version=VersionOut.of(summary.version) if summary.version else None,
        )


class ListsOverviewOut(BaseModel):
    year: int
    years: list[int]
    lists: list[ListSummaryOut]

    @classmethod
    def of(cls, overview: ListsOverview) -> "ListsOverviewOut":
        return cls(
            year=overview.year,
            years=overview.years,
            lists=[ListSummaryOut.of(s) for s in overview.lists],
        )


class EntryChangeOut(BaseModel):
    key: str
    before: EntryOut
    after: EntryOut


class DiffOut(BaseModel):
    old: VersionOut
    new: VersionOut
    added: list[EntryOut]
    removed: list[EntryOut]
    changed: list[EntryChangeOut]

    @classmethod
    def of(cls, diff: DiffView) -> "DiffOut":
        return cls(
            old=VersionOut.of(diff.old),
            new=VersionOut.of(diff.new),
            added=[EntryOut.of(e) for e in diff.added],
            removed=[EntryOut.of(e) for e in diff.removed],
            changed=[
                EntryChangeOut(key=c.key, before=EntryOut.of(c.before), after=EntryOut.of(c.after))
                for c in diff.changed
            ],
        )


class EntryIn(BaseModel):
    version_id: str | None = Field(
        description="The active version the editor saw; null when the list has none yet"
    )
    values: dict[str, Any] = Field(description="The entry's fields (an edit: those to change)")


class VersionRefIn(BaseModel):
    version_id: str = Field(description="The active version the editor saw")


class ChecklistYearOut(BaseModel):
    year: int
    complete: bool
    lists: list[ListSummaryOut]

    @classmethod
    def of(cls, year: ChecklistYear) -> "ChecklistYearOut":
        return cls(
            year=year.year,
            complete=year.complete,
            lists=[ListSummaryOut.of(s) for s in year.lists],
        )


class ConventionsOut(BaseModel):
    customer_id: str
    year: int
    revision: int = Field(description="0 while the customer has no conventions for the year")
    document: dict[str, Any]
    updated_at: datetime | None
    updated_by: str | None

    @classmethod
    def of(cls, view: ConventionsView) -> "ConventionsOut":
        return cls(**{name: getattr(view, name) for name in cls.model_fields})


class ConventionsIn(BaseModel):
    revision: int = Field(ge=0, description="The revision the editor loaded (0 for none)")
    document: dict[str, Any]
