"""The reference data the engine codes with, built from a customer's active code list
versions for a year (plan §4.3).

The bundle is cached by the version IDs it is built from: a new version has a new ID, so an
import or a row edit makes the next request build a fresh bundle, and nothing has to be
invalidated by hand.

The bundle says what the committed `data/bundles/<IČO>/<period>.json` says: the entity, the
period (the newest of the versions'), the source files and the reading warnings in the list
order, and every active entry. Inactive rows are left out (plan §2 decision 57).
"""

from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock

from riso.codelists.application.uow import CodelistsUnitOfWork
from riso.codelists.domain import (
    CUSTOMER_KINDS,
    REQUIRED_CUSTOMER_KINDS,
    AccountEntry,
    BudgetEntry,
    CodeListVersion,
    CostCentreEntry,
    ListKind,
    SeriesEntry,
    TransferEntry,
)
from riso.contracts import Entity, IngestWarning, ReferenceBundle, SourceFile
from riso.identity import Permission
from riso.shared.context import RequestContext
from riso.shared.errors import InvalidState


@dataclass(frozen=True, slots=True)
class BundleEntity:
    """The customer as the bundle names it."""

    ico: str
    name: str
    address: str | None = None


def build_bundle(
    entity: BundleEntity, year: int, versions: Mapping[ListKind, CodeListVersion]
) -> ReferenceBundle:
    """The bundle of the given versions (one per customer kind; a missing optional kind is an
    empty list)."""
    missing = [kind.value for kind in REQUIRED_CUSTOMER_KINDS if kind not in versions]
    if missing:
        raise InvalidState(f"no {', '.join(missing)} list for {year}")
    ordered = [versions[kind] for kind in CUSTOMER_KINDS if kind in versions]
    for version in ordered:
        if version.year != year or version.customer_id is None:
            raise ValueError(f"version {version.id} is not a customer list of {year}")
    periods = [v.period for v in ordered if v.period is not None]
    period = max(periods) if periods else f"{year}-01"

    def active(kind: ListKind) -> list[object]:
        version = versions.get(kind)
        return list(version.active_entries()) if version else []

    return ReferenceBundle(
        bundle_id=f"{entity.ico}/{period}",
        entity=Entity(ico=entity.ico, name=entity.name, address=entity.address),
        period=period,
        sources=[
            SourceFile(name=v.source.name, sha256=v.source.sha256, data_rows=v.source.data_rows)
            for v in ordered
            if v.source is not None
        ],
        accounts=[
            e.to_contract() for e in active(ListKind.ACCOUNTS) if isinstance(e, AccountEntry)
        ],
        budget_positions_expense=[
            e.to_contract() for e in active(ListKind.BUDGET_EXPENSE) if isinstance(e, BudgetEntry)
        ],
        budget_positions_income=[
            e.to_contract() for e in active(ListKind.BUDGET_INCOME) if isinstance(e, BudgetEntry)
        ],
        document_series=[
            e.to_contract() for e in active(ListKind.DOCUMENT_SERIES) if isinstance(e, SeriesEntry)
        ],
        transfers=[
            e.to_contract() for e in active(ListKind.TRANSFERS) if isinstance(e, TransferEntry)
        ],
        cost_centres=[
            e.to_contract() for e in active(ListKind.COST_CENTRES) if isinstance(e, CostCentreEntry)
        ],
        warnings=[
            IngestWarning.model_validate(
                {"code": w.code, "source": w.source, "rows": list(w.rows), "message": w.message}
            )
            for v in ordered
            for w in v.warnings
        ],
    )


CacheKey = tuple[BundleEntity, int, tuple[str, ...]]


class BundleCache:
    """The most recently used bundles, keyed by the entity, the year and the version IDs."""

    def __init__(self, size: int = 32) -> None:
        self._size = size
        self._bundles: OrderedDict[CacheKey, ReferenceBundle] = OrderedDict()
        self._lock = Lock()
        self.builds = 0
        """How many bundles were built rather than taken from the cache."""

    def get(self, key: CacheKey) -> ReferenceBundle | None:
        with self._lock:
            bundle = self._bundles.get(key)
            if bundle is not None:
                self._bundles.move_to_end(key)
            return bundle

    def put(self, key: CacheKey, bundle: ReferenceBundle) -> None:
        with self._lock:
            self.builds += 1
            self._bundles[key] = bundle
            self._bundles.move_to_end(key)
            while len(self._bundles) > self._size:
                self._bundles.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._bundles.clear()


BUNDLES = BundleCache()


def reference_bundle(
    ctx: RequestContext,
    uow: CodelistsUnitOfWork,
    customer_id: str,
    year: int,
    entity: BundleEntity,
    *,
    cache: BundleCache = BUNDLES,
) -> ReferenceBundle:
    """The customer's bundle for the year. Raises `InvalidState` when a list the engine needs
    has no version for the year."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        ids = uow.codelists.active_ids(customer_id, year)
        kinds = [kind for kind in CUSTOMER_KINDS if kind in ids]
        key: CacheKey = (entity, year, tuple(ids[kind] for kind in kinds))
        cached = cache.get(key)
        if cached is not None:
            return cached
        versions = {kind: uow.codelists.get(customer_id, ids[kind]) for kind in kinds}
    bundle = build_bundle(entity, year, versions)
    cache.put(key, bundle)
    return bundle
