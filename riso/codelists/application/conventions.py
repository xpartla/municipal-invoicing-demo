"""A customer's conventions for a year (plan §6.4, decision 56): reading and replacing the
document, and the knowledge the engine codes with (the year's global knowledge merged with
them).

Replacing is audited with the document before and after. A document must merge with the
global knowledge of its year: a rule may only name concepts the lexicon (or the document)
defines, and a local concept may not redefine a global one.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any

from pydantic import ValidationError

from riso.codelists.application.uow import CodelistsUnitOfWork
from riso.codelists.domain import CustomerConventions
from riso.identity import Permission
from riso.knowledge import Conventions, KnowledgeBase, UnknownKnowledge, load_knowledge, merge
from riso.shared.context import RequestContext
from riso.shared.errors import InvalidState, ValidationFailed


@dataclass(frozen=True, slots=True)
class ConventionsView:
    customer_id: str
    year: int
    revision: int
    """0 while the customer has no conventions for the year."""
    document: dict[str, Any]
    updated_at: datetime | None
    updated_by: str | None

    @classmethod
    def of(cls, conventions: CustomerConventions) -> "ConventionsView":
        return cls(
            customer_id=conventions.customer_id,
            year=conventions.year,
            revision=conventions.revision,
            document=_dump(conventions.document),
            updated_at=conventions.updated_at,
            updated_by=conventions.updated_by,
        )

    @classmethod
    def empty(cls, customer_id: str, year: int) -> "ConventionsView":
        return cls(customer_id, year, 0, _dump(Conventions()), None, None)


def _dump(document: Conventions) -> dict[str, Any]:
    return document.model_dump(mode="json")


def _global(year: int) -> KnowledgeBase:
    try:
        return load_knowledge(year)
    except UnknownKnowledge as exc:
        raise InvalidState(f"no global knowledge for {year}") from exc


def parse_conventions(year: int, document: Mapping[str, Any]) -> Conventions:
    """The document validated, and checked to merge with the year's global knowledge."""
    try:
        conventions = Conventions.model_validate(dict(document))
    except ValidationError as exc:
        raise ValidationFailed.from_pydantic("invalid conventions", exc.errors()) from exc
    knowledge = _global(year)
    try:
        merge(knowledge, conventions)
    except ValueError as exc:  # a ValidationError of the merged model is one too
        detail = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
        raise ValidationFailed.on("concepts", detail, "conventions") from exc
    return conventions


def get_conventions(
    ctx: RequestContext, uow: CodelistsUnitOfWork, customer_id: str, year: int
) -> ConventionsView:
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        conventions = uow.conventions.get(customer_id, year)
    if conventions is None:
        return ConventionsView.empty(customer_id, year)
    return ConventionsView.of(conventions)


def set_conventions(
    ctx: RequestContext,
    uow: CodelistsUnitOfWork,
    customer_id: str,
    year: int,
    document: Mapping[str, Any],
    *,
    expected_revision: int | None = None,
) -> ConventionsView:
    """Replaces the customer's conventions for the year. `expected_revision` is the
    revision the editor loaded (0 for none); a different one is a conflict."""
    ctx.require(Permission.CODELISTS_EDIT, customer_id)
    parsed = parse_conventions(year, document)
    with uow:
        now = uow.clock.now()
        current = uow.conventions.get(customer_id, year)
        if current is None:
            if expected_revision not in (None, 0):
                raise InvalidState(f"no conventions for {year} to replace")
            current = CustomerConventions.create(customer_id, year, parsed, now, ctx.actor_id)
            before: dict[str, Any] | None = None
        else:
            before = _dump(current.document)
            if not current.replace(parsed, now, ctx.actor_id, expected_revision=expected_revision):
                return ConventionsView.of(current)
        uow.conventions.save(current)
        uow.audit.record(
            ctx,
            "conventions.updated",
            target_type="conventions",
            target_id=f"{customer_id}/{year}",
            customer_id=customer_id,
            details={
                "year": year,
                "revision": current.revision,
                "before": before,
                "after": _dump(current.document),
            },
        )
        uow.commit()
    return ConventionsView.of(current)


class KnowledgeCache:
    """Merged knowledge by customer, year and conventions revision."""

    def __init__(self, size: int = 32) -> None:
        self._size = size
        self._items: dict[tuple[str, int, int], KnowledgeBase] = {}
        self._lock = Lock()

    def get(self, key: tuple[str, int, int]) -> KnowledgeBase | None:
        with self._lock:
            return self._items.get(key)

    def put(self, key: tuple[str, int, int], knowledge: KnowledgeBase) -> None:
        with self._lock:
            if len(self._items) >= self._size:
                self._items.pop(next(iter(self._items)))
            self._items[key] = knowledge


KNOWLEDGE = KnowledgeCache()


def customer_knowledge(
    ctx: RequestContext,
    uow: CodelistsUnitOfWork,
    customer_id: str,
    year: int,
    *,
    cache: KnowledgeCache = KNOWLEDGE,
) -> tuple[KnowledgeBase, int]:
    """The knowledge the engine codes the customer's invoices of the year with, and the
    conventions revision it includes (0 for none)."""
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        conventions = uow.conventions.get(customer_id, year)
    revision = conventions.revision if conventions else 0
    key = (customer_id, year, revision)
    knowledge = cache.get(key)
    if knowledge is None:
        knowledge = merge(_global(year), conventions.document if conventions else Conventions())
        cache.put(key, knowledge)
    return knowledge, revision
