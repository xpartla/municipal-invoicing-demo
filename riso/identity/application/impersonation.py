"""Impersonation (plan §5.4, decisions 5–6).

An admin acts as one user, to see exactly what that user sees, with writes allowed. It needs
a reason, never targets another admin, and ends on request, at logout, or after 60 minutes.
While it lasts, requests act as the user, and every audit entry carries both the user (the
actor) and the admin (the real actor). The user's own credential endpoints refuse (403).
"""

from riso.identity.application.auth import IdentityUnitOfWork
from riso.identity.domain import Permission
from riso.shared.context import RequestContext
from riso.shared.errors import InvalidState, PermissionDenied
from riso.shared.values import clean_name

MAX_REASON = 500


def start_impersonation(
    ctx: RequestContext,
    uow: IdentityUnitOfWork,
    *,
    session_id: str,
    user_id: str,
    reason: str,
) -> None:
    ctx.require(Permission.USERS_IMPERSONATE)
    if ctx.impersonating:
        raise InvalidState("already impersonating")
    why = clean_name(reason, "reason", max_length=MAX_REASON)
    with uow:
        session = uow.sessions.get(session_id)
        target = uow.users.get(user_id)
        if target.is_admin:
            raise PermissionDenied("an admin cannot be impersonated")
        if not target.can_log_in:
            raise InvalidState(f"user {target.id} cannot log in")
        session.start_impersonation(target.id, why, uow.clock.now())
        uow.sessions.save(session)
        uow.audit.record(
            ctx,
            "impersonation.started",
            target_type="user",
            target_id=target.id,
            details={"session_id": session.id, "reason": why},
        )
        uow.commit()


def end_impersonation(ctx: RequestContext, uow: IdentityUnitOfWork, *, session_id: str) -> None:
    """Ends it from inside: `ctx` acts as the user, with the admin as the real actor."""
    with uow:
        session = uow.sessions.get(session_id)
        if not session.impersonating:
            raise InvalidState("not impersonating")
        user_id = session.end_impersonation()
        uow.sessions.save(session)
        uow.audit.record(
            ctx,
            "impersonation.ended",
            target_type="user",
            target_id=user_id,
            details={"session_id": session.id},
        )
        uow.commit()
