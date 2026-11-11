"""The reporting API: the customer's storage listing (Úložisko)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from riso.api.deps import Caller, ServicesDep, check_csrf, customer_context
from riso.identity import Permission
from riso.reporting.application import FileKind, FileListing, list_files

router = APIRouter(prefix="/api", dependencies=[Depends(check_csrf)], tags=["reporting"])

MAX_PAGE = 200


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FileOut(_Out):
    kind: FileKind
    id: str
    name: str
    media_type: str
    size: int
    created_at: datetime
    created_by: str | None
    invoice_id: str | None
    detail: str | None


class KindTotalOut(_Out):
    count: int
    size: int


class FilesOut(_Out):
    """The page of files (`items`) of `total` matching ones; `size` and `kinds` count every
    file of the customer. A file downloads through its owner: `documents.file`,
    `imports.file` or `exports.file` with the file's `id`."""

    items: list[FileOut]
    total: int
    size: int
    kinds: dict[FileKind, KindTotalOut]

    @classmethod
    def of(cls, listing: FileListing) -> "FilesOut":
        return cls(
            items=[
                FileOut(
                    kind=f.kind,
                    id=f.id,
                    name=f.name,
                    media_type=f.media_type,
                    size=f.size,
                    created_at=f.created_at,
                    created_by=f.created_by,
                    invoice_id=f.invoice_id,
                    detail=f.detail,
                )
                for f in listing.items
            ],
            total=listing.total,
            size=listing.size,
            kinds={k: KindTotalOut(count=t.count, size=t.size) for k, t in listing.kinds.items()},
        )


@router.get("/customers/{customer_id}/files", name="files.list")
def files(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
    kind: FileKind | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
) -> FilesOut:
    """Every file the customer's storage keeps (Úložisko), the newest first: uploaded
    invoices (`document`, with the invoice), import files and export files."""
    listing = list_files(
        caller.ctx,
        lambda: services.uow(immediate=False),
        customer_id,
        kind=kind,
        offset=(page - 1) * size,
        limit=size,
    )
    return FilesOut.of(listing)
