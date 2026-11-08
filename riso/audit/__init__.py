"""The audit context: the append-only log of who did what, as whom, in which customer. Main
aggregates: AuditEvent. Writing goes through the `AuditRecorder` port of `riso.shared`, so
every context records without importing this one. This module is the context's public surface:
other contexts import only what it exports (its application API), never its domain,
infrastructure or api modules. See plan §4.2 and guide §6.1."""

from riso.audit.application import AuditLog, AuditUnitOfWork, list_events
from riso.audit.domain import AuditEvent, AuditFilter

__all__ = ["AuditEvent", "AuditFilter", "AuditLog", "AuditUnitOfWork", "list_events"]
