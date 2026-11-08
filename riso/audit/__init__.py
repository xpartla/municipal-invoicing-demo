"""The audit context: the append-only audit log: who did what, as whom, in which customer, and from
which request. Main aggregates: AuditEvent. This module is the context's public surface: other
contexts import only what it exports (its application API), never its domain, infrastructure or
api modules. See plan §4.2 and guide §6.1."""
