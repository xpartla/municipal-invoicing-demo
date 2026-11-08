"""Entities, value objects, domain services, events, repository protocols and errors of the identity
context. Pure Python: it imports only this context's domain, `riso.shared` and `riso.contracts`;
never SQLAlchemy, FastAPI, `riso.platform` or I/O libraries."""

from riso.identity.domain.email import Email
from riso.identity.domain.membership import Membership, MembershipScope
from riso.identity.domain.passwords import PasswordHasher, PasswordPolicy
from riso.identity.domain.permissions import (
    ROLE_PERMISSIONS,
    ROLE_SCOPE,
    Permission,
    Role,
    ScopeKind,
)
from riso.identity.domain.user import TRANSITIONS, User, UserStatus

__all__ = [
    "ROLE_PERMISSIONS",
    "ROLE_SCOPE",
    "TRANSITIONS",
    "Email",
    "Membership",
    "MembershipScope",
    "PasswordHasher",
    "PasswordPolicy",
    "Permission",
    "Role",
    "ScopeKind",
    "User",
    "UserStatus",
]
