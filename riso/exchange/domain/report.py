"""The dry run's report (plan §9.2 step 3), stored as JSON on the import run.

It says how many rows were read and how many entries they make, lists the errors (each with
its rows and field) and the warnings, the difference from the active version, and a preview
of the first entries.

Errors are of two kinds (plan §2 decision 58). A hard error (an unreadable row, a malformed
code, a file of another customer's) always refuses applying. An error against the year's
global lists (an EK, zdroj or function the lists lack) is `confirmable`: applying it needs
the explicit confirmation "import anyway", which is audited.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SAMPLE = 50
"""How many added, removed and changed entries the report lists (it counts them all)."""
PREVIEW = 20


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Literal["error", "warning"]
    code: str
    message: str
    """English, for the log and the API; the UI words it from `code` and the fields below."""
    rows: tuple[int, ...] = ()
    field: str | None = None
    key: str | None = None
    value: str | None = None
    confirmable: bool = False
    """An error against the global lists, which confirming lets through."""


class EntryChangeSample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    before: dict[str, Any]
    after: dict[str, Any]


class ReportDiff(BaseModel):
    """The difference from the active version (none: everything is new)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_version_id: str | None = None
    base_number: int | None = None
    added: int = 0
    removed: int = 0
    changed: int = 0
    unchanged: int = 0
    added_sample: tuple[dict[str, Any], ...] = ()
    removed_sample: tuple[dict[str, Any], ...] = ()
    changed_sample: tuple[EntryChangeSample, ...] = ()


class DryRunReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    checked_at: datetime
    rows_read: int
    entries: int
    errors: tuple[Issue, ...] = ()
    warnings: tuple[Issue, ...] = ()
    diff: ReportDiff = Field(default_factory=ReportDiff)
    preview: tuple[dict[str, Any], ...] = ()
    file_ico: str | None = None
    period: str | None = None
    """The month the file describes, from the file; the new version's period."""

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def hard_errors(self) -> tuple[Issue, ...]:
        return tuple(e for e in self.errors if not e.confirmable)

    @property
    def confirmable_errors(self) -> tuple[Issue, ...]:
        return tuple(e for e in self.errors if e.confirmable)

    def can_apply(self, *, confirm_errors: bool) -> bool:
        """Without errors, or with only confirmable ones and the confirmation."""
        return not self.hard_errors and (confirm_errors or not self.errors)
