"""Úložisko (plan §10.7): every file the customer's storage keeps, by kind, with what uses it
and the total size. Uploaded invoices come from the intake context, import and export files
from the exchange context."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from riso.exchange import RunFilesUnitOfWork, customer_run_files
from riso.identity import Permission
from riso.intake import IntakeUnitOfWork, customer_documents
from riso.shared.context import RequestContext

FileKind = Literal["document", "import", "export"]
KINDS: tuple[FileKind, ...] = ("document", "import", "export")


class FilesUnitOfWork(IntakeUnitOfWork, RunFilesUnitOfWork, Protocol):
    pass


@dataclass(frozen=True, slots=True)
class FileView:
    kind: FileKind
    id: str
    """The document's or the run's ID: what the file is downloaded through."""
    name: str
    media_type: str
    size: int
    created_at: datetime
    created_by: str | None
    invoice_id: str | None = None
    """The invoice an uploaded document became."""
    detail: str | None = None
    """An import's type, or how many invoices an export holds."""


@dataclass(frozen=True, slots=True)
class KindTotal:
    count: int
    size: int


@dataclass(frozen=True, slots=True)
class FileListing:
    items: list[FileView]
    total: int
    """Files matching the filter (the page holds `items`)."""
    size: int
    """Bytes of every file of the customer."""
    kinds: dict[FileKind, KindTotal]


def list_files(
    ctx: RequestContext,
    uow_factory: Callable[[], FilesUnitOfWork],
    customer_id: str,
    *,
    kind: FileKind | None = None,
    offset: int = 0,
    limit: int = 50,
) -> FileListing:
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    files = [
        FileView(
            kind="document",
            id=d.id,
            name=d.filename,
            media_type=d.media_type.value,
            size=d.size,
            created_at=d.uploaded_at,
            created_by=d.uploaded_by,
            invoice_id=d.invoice_id,
        )
        for d in customer_documents(ctx, uow_factory(), customer_id)
    ]
    files.extend(
        FileView(
            kind=f.kind,
            id=f.run_id,
            name=f.name,
            media_type=f.media_type,
            size=f.size,
            created_at=f.created_at,
            created_by=f.created_by,
            detail=f.detail,
        )
        for f in customer_run_files(ctx, uow_factory(), customer_id)
    )
    files.sort(key=lambda f: (f.created_at, f.id), reverse=True)
    kinds = {
        k: KindTotal(
            sum(1 for f in files if f.kind == k), sum(f.size for f in files if f.kind == k)
        )
        for k in KINDS
    }
    chosen = [f for f in files if kind is None or f.kind == kind]
    return FileListing(
        items=chosen[offset : offset + limit],
        total=len(chosen),
        size=sum(f.size for f in files),
        kinds=kinds,
    )
