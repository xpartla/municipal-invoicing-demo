"""The jobs context: background work: the job queue, claiming and retries, the registry of job
kinds, and the worker. Main aggregates: Job. This module is the context's public surface: other
contexts import only what it exports (its application API), never its domain, infrastructure or
api modules. See plan §4.2 and guide §6.1."""
