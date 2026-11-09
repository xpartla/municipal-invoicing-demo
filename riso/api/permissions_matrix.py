"""Who may call each API route (guide §6.5).

Every route under `/api` has a unique `name` and an entry here: the permission it needs and
the scope the permission is checked in. `tests/api/test_permissions.py` fails for a route
without an entry, and for an entry without a route. From P2-M1 the same test generates the
role × route × own/foreign customer matrix from this table.

Each route declares its access with one dependency from `riso.api.deps` (`customer_context`
and the others), and the matrix test checks that the dependency and the entry agree. The
demo's routes are `public` until P2-M4 replaces them: the demo has no logins.
"""

from dataclasses import dataclass
from enum import StrEnum

from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts

from riso.identity.domain import Permission


class Scope(StrEnum):
    PUBLIC = "public"
    """Anyone, logged in or not."""
    SELF = "self"
    """The caller's own account (`/api/me/…`, `/api/auth/…`)."""
    CUSTOMER = "customer"
    """A customer the caller can access (`/api/customers/{customer_id}/…`)."""
    PROVIDER = "provider"
    """A service provider the caller belongs to (`/api/providers/{provider_id}/…`)."""
    PLATFORM = "platform"
    """Platform administration (`/api/admin/…`)."""


@dataclass(frozen=True, slots=True)
class RouteAccess:
    scope: Scope
    permission: Permission | None = None
    """The permission checked in the scope; None only for public and self routes."""
    personal: bool = False
    """A self route that changes a credential, refused while impersonating (plan §5.4)."""


def public() -> RouteAccess:
    return RouteAccess(Scope.PUBLIC)


def own(*, personal: bool = False) -> RouteAccess:
    return RouteAccess(Scope.SELF, personal=personal)


def customer(permission: Permission) -> RouteAccess:
    return RouteAccess(Scope.CUSTOMER, permission)


def provider(permission: Permission) -> RouteAccess:
    return RouteAccess(Scope.PROVIDER, permission)


def platform(permission: Permission) -> RouteAccess:
    return RouteAccess(Scope.PLATFORM, permission)


MATRIX: dict[str, RouteAccess] = {
    # Identity: logging in and out, the caller's own account.
    "auth.login": public(),
    "auth.logout": own(),
    "auth.logout_all": own(personal=True),
    "me.get": own(),
    "me.sessions": own(),
    "me.change_password": own(personal=True),
    "me.request_email_change": own(personal=True),
    "auth.token_info": public(),
    "auth.accept_invitation": public(),
    "auth.request_reset": public(),
    "auth.reset_password": public(),
    "auth.confirm_email_change": public(),
    "me.end_impersonation": own(),
    "me.update": own(),
    "users.impersonate": platform(Permission.USERS_IMPERSONATE),
    "users.list": platform(Permission.USERS_ADMINISTER),
    "users.lock": platform(Permission.USERS_ADMINISTER),
    "users.unlock": platform(Permission.USERS_ADMINISTER),
    "users.force_logout": platform(Permission.USERS_ADMINISTER),
    "users.delete": platform(Permission.USERS_DELETE),
    "users.restore": platform(Permission.USERS_DELETE),
    "users.purge": platform(Permission.USERS_DELETE),
    # A customer's logins.
    "logins.invite": customer(Permission.LOGINS_MANAGE),
    "logins.deactivate": customer(Permission.LOGINS_MANAGE),
    "logins.reactivate": customer(Permission.LOGINS_MANAGE),
    "logins.send_link": customer(Permission.LOGINS_MANAGE),
    # Platform tools.
    "outbox.list": platform(Permission.OUTBOX_READ),
    "outbox.get": platform(Permission.OUTBOX_READ),
    "audit.list": platform(Permission.AUDIT_READ),
    # exchange: imports and templates
    "imports.upload": customer(Permission.CODELISTS_EDIT),
    "imports.list": customer(Permission.CUSTOMER_READ),
    "imports.get": customer(Permission.CUSTOMER_READ),
    "imports.file": customer(Permission.CUSTOMER_READ),
    "imports.preview": customer(Permission.CODELISTS_EDIT),
    "imports.map": customer(Permission.CODELISTS_EDIT),
    "imports.dry_run": customer(Permission.CODELISTS_EDIT),
    "imports.apply": customer(Permission.CODELISTS_EDIT),
    "imports.cancel": customer(Permission.CODELISTS_EDIT),
    "imports.save_template": customer(Permission.TEMPLATES_USE),
    "templates.list": customer(Permission.TEMPLATES_USE),
    "templates.update": customer(Permission.TEMPLATES_USE),
    "templates.delete": customer(Permission.TEMPLATES_USE),
    "admin_imports.upload": platform(Permission.GLOBAL_CODELISTS),
    "admin_imports.list": platform(Permission.GLOBAL_CODELISTS),
    "admin_imports.get": platform(Permission.GLOBAL_CODELISTS),
    "admin_imports.file": platform(Permission.GLOBAL_CODELISTS),
    "admin_imports.preview": platform(Permission.GLOBAL_CODELISTS),
    "admin_imports.map": platform(Permission.GLOBAL_CODELISTS),
    "admin_imports.dry_run": platform(Permission.GLOBAL_CODELISTS),
    "admin_imports.apply": platform(Permission.GLOBAL_CODELISTS),
    "admin_imports.cancel": platform(Permission.GLOBAL_CODELISTS),
    "admin_imports.save_template": platform(Permission.TEMPLATES_CREATE_GLOBAL),
    "admin_templates.list": platform(Permission.GLOBAL_CODELISTS),
    "admin_templates.update": platform(Permission.TEMPLATES_CREATE_GLOBAL),
    "admin_templates.delete": platform(Permission.TEMPLATES_CREATE_GLOBAL),
    "exports.preview": customer(Permission.INVOICES_PROCESS),
    "exports.start": customer(Permission.INVOICES_PROCESS),
    "exports.list": customer(Permission.CUSTOMER_READ),
    "exports.get": customer(Permission.CUSTOMER_READ),
    "exports.file": customer(Permission.CUSTOMER_READ),
    # jobs
    "jobs.get_customer": customer(Permission.CUSTOMER_READ),
    # Code lists.
    "codelists.health": customer(Permission.CUSTOMER_READ),
    "codelists.overview": customer(Permission.CUSTOMER_READ),
    "codelists.entries": customer(Permission.CUSTOMER_READ),
    "codelists.versions": customer(Permission.CUSTOMER_READ),
    "codelists.diff": customer(Permission.CUSTOMER_READ),
    "codelists.add_entry": customer(Permission.CODELISTS_EDIT),
    "codelists.edit_entry": customer(Permission.CODELISTS_EDIT),
    "codelists.deactivate_entry": customer(Permission.CODELISTS_EDIT),
    "codelists.reactivate_entry": customer(Permission.CODELISTS_EDIT),
    "conventions.get": customer(Permission.CUSTOMER_READ),
    "conventions.set": customer(Permission.CODELISTS_EDIT),
    "parameters.get": customer(Permission.CUSTOMER_READ),
    "parameters.set": customer(Permission.CODELISTS_EDIT),
    "admin_codelists.checklist": platform(Permission.GLOBAL_CODELISTS),
    "admin_codelists.entries": platform(Permission.GLOBAL_CODELISTS),
    "admin_codelists.versions": platform(Permission.GLOBAL_CODELISTS),
    # Invoicing.
    "coding.code": customer(Permission.INVOICES_PROCESS),
    "invoices.list": customer(Permission.CUSTOMER_READ),
    "invoices.suppliers": customer(Permission.CUSTOMER_READ),
    "invoices.get": customer(Permission.CUSTOMER_READ),
    "invoices.history": customer(Permission.CUSTOMER_READ),
    "invoices.bulk_pay": customer(Permission.INVOICES_PROCESS),
    "invoices.bulk_recode": customer(Permission.INVOICES_PROCESS),
    "invoices.bulk_discard": customer(Permission.INVOICES_PROCESS),
    "invoices.create": customer(Permission.INVOICES_PROCESS),
    "invoices.check": customer(Permission.INVOICES_PROCESS),
    "invoices.recode": customer(Permission.INVOICES_PROCESS),
    "invoices.line": customer(Permission.INVOICES_PROCESS),
    "invoices.preview_booking": customer(Permission.INVOICES_PROCESS),
    "invoices.book": customer(Permission.INVOICES_PROCESS),
    "invoices.unbook": customer(Permission.INVOICES_PROCESS),
    "invoices.discard": customer(Permission.INVOICES_PROCESS),
    "invoices.pay": customer(Permission.INVOICES_PROCESS),
    # Number series.
    "number_series.list": customer(Permission.CUSTOMER_READ),
    "number_series.set_last_used": customer(Permission.CODELISTS_EDIT),
    # Tenancy.
    "customers.get": customer(Permission.CUSTOMER_READ),
    "customers.update_contact": customer(Permission.CUSTOMER_EDIT_CONTACT),
    "customers.update_identity": customer(Permission.CUSTOMER_EDIT_IDENTITY),
    "customers.assign_variable_number": customer(Permission.CUSTOMER_ASSIGN_VARIABLE_NUMBER),
    "customers.delete": customer(Permission.CUSTOMERS_DELETE),
    "customers.restore": customer(Permission.CUSTOMERS_DELETE),
    "customers.purge": customer(Permission.CUSTOMERS_DELETE),
    "customers.create": platform(Permission.CUSTOMERS_CREATE),
    "customers.copy": platform(Permission.CUSTOMERS_CREATE),
    "customers.directory": platform(Permission.PROVIDER_OVERVIEW),
    "customers.assign_provider": platform(Permission.PROVIDERS_MANAGE),
    "customers.unassign_provider": platform(Permission.PROVIDERS_MANAGE),
    "providers.get": provider(Permission.PROVIDER_OVERVIEW),
    "providers.directory": provider(Permission.PROVIDER_OVERVIEW),
    "providers.create_customer": provider(Permission.CUSTOMERS_CREATE),
    "providers.copy_customer": provider(Permission.CUSTOMERS_CREATE),
    "providers.list": platform(Permission.PROVIDERS_MANAGE),
    "providers.create": platform(Permission.PROVIDERS_MANAGE),
    "providers.remove": platform(Permission.PROVIDERS_MANAGE),
    "providers.add_staff": platform(Permission.PROVIDERS_MANAGE),
    "providers.remove_staff": platform(Permission.PROVIDERS_MANAGE),
    # The demo (P2-M4 replaces these).
    "legacy.entities": public(),
    "legacy.reference": public(),
    "legacy.invoices": public(),
    "legacy.invoice": public(),
    "legacy.code": public(),
    "legacy.line": public(),
    "legacy.feedback": public(),
    "legacy.feedback_log": public(),
    "legacy.counters": public(),
    "legacy.eval": public(),
}


@dataclass(frozen=True, slots=True)
class ApiRoute:
    """A route under `/api`, as the app serves it (included routers flattened)."""

    name: str
    path: str
    methods: frozenset[str]
    route: APIRoute


def api_routes(app: FastAPI) -> list[ApiRoute]:
    """Every `/api` route of the app. FastAPI 0.143 keeps included routers as their own
    entries in `app.routes`, so they are walked through `iter_route_contexts`."""
    found = []
    for context in iter_route_contexts(app.routes):
        route = context.original_route
        path = context.path or ""
        if isinstance(route, APIRoute) and path.startswith("/api"):
            found.append(ApiRoute(route.name, path, frozenset(route.methods or ()), route))
    return found
