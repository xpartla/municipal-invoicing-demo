"""The identity context: logins: users, passwords, sessions, single-use tokens (invitation,
password reset, email change), roles and their permissions, and admin impersonation. Main
aggregates: User, Session, Token. This module is the context's public surface: other contexts
import only what it exports (its application API), never its domain, infrastructure or api
modules. See plan §4.2 and guide §6.1."""
