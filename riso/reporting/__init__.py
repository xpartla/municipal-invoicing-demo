"""The reporting context: read-only queries behind the dashboards: the customer's Domov, the
provider's overview of its customers, and the platform counts. It has no domain layer: it only
reads. This module is the context's public surface: other contexts import only what it exports
(its application API), never its domain, infrastructure or api modules. See plan §4.2 and guide
§6.1."""
