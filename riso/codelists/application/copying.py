"""Copying a customer's code lists and conventions of one year to another customer (plan §9.3,
P2-M3-T06): the customer copy job calls these inside its unit of work.

Each list the source has for the year becomes version 1 of the target's list, with origin
`copy`, the same entries, and the source version's period, source file and warnings (the
lists come from the same files). A list the target already has is left alone, so a copy job
that runs again changes nothing. The caller commits and audits.
"""

from riso.codelists.application.lists import VersionView
from riso.codelists.application.uow import CodelistsUnitOfWork
from riso.codelists.domain import CodeListVersion, CustomerConventions, ListKind, VersionOrigin
from riso.identity import Permission
from riso.shared.context import RequestContext


def _require(ctx: RequestContext, source_id: str, target_id: str) -> None:
    ctx.require(Permission.CUSTOMER_READ, source_id)
    ctx.require(Permission.CODELISTS_EDIT, target_id)


def copy_lists(
    ctx: RequestContext, uow: CodelistsUnitOfWork, source_id: str, target_id: str, year: int
) -> list[VersionView]:
    """The target's new versions, one per list the source has for the year and the target
    does not."""
    _require(ctx, source_id, target_id)
    made = []
    for kind in ListKind:
        if kind.is_global:
            continue
        source = uow.codelists.active(source_id, kind, year)
        if source is None or uow.codelists.active(target_id, kind, year) is not None:
            continue
        version = CodeListVersion.first(
            uow.ids.new(),
            kind,
            target_id,
            year,
            source.entries,
            origin=VersionOrigin.COPY,
            at=uow.clock.now(),
            actor=ctx.actor_id,
            period=source.period,
            source=source.source,
            warnings=source.warnings,
            note=f"copy of version {source.number} of customer {source_id}",
        )
        uow.codelists.add(version)
        made.append(VersionView.of(version.info()))
    return made


def copy_conventions(
    ctx: RequestContext, uow: CodelistsUnitOfWork, source_id: str, target_id: str, year: int
) -> bool:
    """Gives the target the source's conventions of the year. False when the source has
    none or the target already has some."""
    _require(ctx, source_id, target_id)
    source = uow.conventions.get(source_id, year)
    if source is None or uow.conventions.get(target_id, year) is not None:
        return False
    uow.conventions.save(
        CustomerConventions.create(target_id, year, source.document, uow.clock.now(), ctx.actor_id)
    )
    return True
