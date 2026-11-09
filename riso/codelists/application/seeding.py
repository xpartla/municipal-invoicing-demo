"""A committed reference bundle as the first versions of a customer's lists (`riso seed`;
plan §4.3). P2-M3's import tool makes versions from the raw exports instead."""

from datetime import datetime

from riso.codelists.domain import (
    AccountEntry,
    BudgetEntry,
    CodeListVersion,
    CostCentreEntry,
    Entry,
    ListKind,
    ListWarning,
    SeriesEntry,
    SourceRef,
    TransferEntry,
    VersionOrigin,
)
from riso.contracts import ReferenceBundle
from riso.shared.ids import IdGenerator

SOURCE_ORDER = (
    ListKind.ACCOUNTS,
    ListKind.BUDGET_EXPENSE,
    ListKind.BUDGET_INCOME,
    ListKind.DOCUMENT_SERIES,
)
"""The lists `riso ingest` reads a file for, in the order the bundle lists the files."""


def versions_from_bundle(
    bundle: ReferenceBundle,
    customer_id: str,
    ids: IdGenerator,
    at: datetime,
    *,
    origin: VersionOrigin = VersionOrigin.SEED,
    actor: str | None = None,
) -> list[CodeListVersion]:
    """Version 1 of each list the bundle has entries for, with the bundle's period, each
    list's source file and the warnings about that file."""
    if len(bundle.sources) > len(SOURCE_ORDER):
        raise ValueError(f"bundle {bundle.bundle_id} has more sources than lists")
    sources = dict(zip(SOURCE_ORDER, bundle.sources, strict=False))
    by_source: dict[str, list[ListWarning]] = {}
    for warning in bundle.warnings:
        by_source.setdefault(warning.source, []).append(
            ListWarning(warning.code, warning.source, tuple(warning.rows), warning.message)
        )
    unmatched = set(by_source) - {s.name for s in bundle.sources}
    if unmatched:
        raise ValueError(f"bundle {bundle.bundle_id} warns about unknown sources {unmatched}")
    entries: dict[ListKind, list[Entry]] = {
        ListKind.ACCOUNTS: [AccountEntry.of(a) for a in bundle.accounts],
        ListKind.BUDGET_EXPENSE: [BudgetEntry.of(p) for p in bundle.budget_positions_expense],
        ListKind.BUDGET_INCOME: [BudgetEntry.of(p) for p in bundle.budget_positions_income],
        ListKind.DOCUMENT_SERIES: [SeriesEntry.of(s) for s in bundle.document_series],
        ListKind.TRANSFERS: [TransferEntry.of(t) for t in bundle.transfers],
        ListKind.COST_CENTRES: [CostCentreEntry.of(c) for c in bundle.cost_centres],
    }
    year = int(bundle.period[:4])
    versions = []
    for kind, items in entries.items():
        if not items:
            continue
        source = sources.get(kind)
        versions.append(
            CodeListVersion.first(
                ids.new(),
                kind,
                customer_id,
                year,
                items,
                origin=origin,
                at=at,
                actor=actor,
                period=bundle.period,
                source=SourceRef(source.name, source.sha256, source.data_rows) if source else None,
                warnings=by_source.get(source.name, []) if source else [],
                note=f"from bundle {bundle.bundle_id}",
            )
        )
    return versions
