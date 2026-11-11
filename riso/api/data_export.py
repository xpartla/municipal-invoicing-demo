"""The exchange context's `CustomerDump` port on the database (the customer data export, plan
§10.9, §12, decision 67): every row with the customer's ID in every table of the metadata, the
customer and its provider, its members' accounts without credentials, and the keys of the files
its documents, imports and exports keep. The tables are found from the metadata, so a table
added later is exported without a change here. It lives in the composition root, the one place
that may read every context's tables."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Table, select
from sqlalchemy.orm import Session

from riso.exchange.application.data_export import CustomerData
from riso.platform.db import metadata

OMITTED_COLUMNS = {
    "users": {"password_hash"},
    "mail_outbox": {"body"},
}
"""Credentials, and the mail bodies, which carry sign-in links."""

FILE_COLUMNS = {
    "documents": "storage_key",
    "import_runs": "file_key",
    "export_runs": "file_key",
}
"""Where the customer's stored files are named."""


def _json(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def customer_tables() -> list[Table]:
    """Every table with a `customer_id` column, by name."""
    return sorted(
        (t for t in metadata.tables.values() if "customer_id" in t.columns), key=lambda t: t.name
    )


class SqlCustomerDump:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _rows(self, table: Table, *where: Any) -> list[dict[str, Any]]:
        omitted = OMITTED_COLUMNS.get(table.name, set())
        columns = [c for c in table.columns if c.name not in omitted]
        order = list(table.primary_key.columns) or columns[:1]
        found = self._session.execute(select(*columns).where(*where).order_by(*order))
        return [{k: _json(v) for k, v in row._mapping.items()} for row in found]

    def exists(self, customer_id: str) -> bool:
        customers = metadata.tables["customers"]
        found = self._session.execute(
            select(customers.c.id).where(customers.c.id == customer_id)
        ).first()
        return found is not None

    def read(self, customer_id: str) -> CustomerData:
        tables: dict[str, list[dict[str, Any]]] = {}
        customers = metadata.tables["customers"]
        tables["customers"] = self._rows(customers, customers.c.id == customer_id)
        for table in customer_tables():
            tables[table.name] = self._rows(table, table.c.customer_id == customer_id)
        providers = metadata.tables["service_providers"]
        provider_ids = [r["provider_id"] for r in tables.get("provider_assignments", [])]
        tables["service_providers"] = (
            self._rows(providers, providers.c.id.in_(provider_ids)) if provider_ids else []
        )
        memberships = metadata.tables["memberships"]
        tables["memberships"] = self._rows(
            memberships,
            memberships.c.scope_kind == "customer",
            memberships.c.scope_id == customer_id,
        )
        users = metadata.tables["users"]
        user_ids = sorted({r["user_id"] for r in tables["memberships"]})
        tables["users"] = self._rows(users, users.c.id.in_(user_ids)) if user_ids else []
        keys = sorted(
            {
                row[column]
                for name, column in FILE_COLUMNS.items()
                for row in tables.get(name, [])
                if row.get(column)
            }
        )
        label = str(tables["customers"][0]["ico"]) if tables["customers"] else customer_id
        return CustomerData(customer_id, label, tables=tables, file_keys=tuple(keys))
