"""The identity context: logins: users, passwords, sessions, single-use tokens (invitation,
password reset, email change), memberships with their roles and permissions, the access
policy, and admin impersonation. Main aggregates: User (with its memberships), Session,
Token. This module is the context's public surface: other contexts import only what it
exports (its application API), never its domain, infrastructure or api modules. See plan
§4.2 and guide §6.1."""

from riso.identity.domain import Permission, Role, ScopeKind

__all__ = ["Permission", "Role", "ScopeKind"]
