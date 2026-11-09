"""Ports of the exchange context: what its use cases need from adapters."""

from typing import Protocol

from riso.exchange.domain.table import ReadOptions, Workbook


class TableReader(Protocol):
    """Reads an import file (CSV, XLSX or XLS, recognised by content) into a workbook.
    Raises `ValidationFailed` for a file it cannot read."""

    def read(self, data: bytes, options: ReadOptions | None = None) -> Workbook: ...
