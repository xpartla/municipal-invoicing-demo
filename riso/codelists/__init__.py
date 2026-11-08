"""The codelists context: code lists (číselníky): the global lists per year (EK, COFOG, funding
sources, the framework chart) and each customer's versioned lists, their validation against the
global ones, and the reference bundle the engine codes with. Main aggregates: CodeListVersion.
This module is the context's public surface: other contexts import only what it exports (its
application API), never its domain, infrastructure or api modules. See plan §4.2 and guide §6.1."""
