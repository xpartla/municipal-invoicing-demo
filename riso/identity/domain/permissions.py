"""Roles and permissions (plan §5.1–5.2).

Every check names a permission, never a role, so custom roles can later be data. A role is
held in one kind of scope: the customer roles in a customer, the staff role in a service
provider, the admin role on the platform. Where a role's permissions apply follows from its
scope (the access policy, `riso.identity.application.access`):

- a customer role's permissions apply in its customer;
- the staff role's apply in its provider and in the customers assigned to that provider;
- the admin role's apply everywhere.

The admin holds every permission. `tests/unit/identity/test_permissions.py` checks the
mapping against plan §5.2 row by row.
"""

from enum import StrEnum


class ScopeKind(StrEnum):
    CUSTOMER = "customer"
    PROVIDER = "provider"
    PLATFORM = "platform"


class Role(StrEnum):
    CUSTOMER_VIEWER = "customer_viewer"
    """Iba na čítanie."""
    CUSTOMER_USER = "customer_user"
    """Používateľ."""
    PROVIDER_STAFF = "provider_staff"
    """Servisný účet."""
    PLATFORM_ADMIN = "platform_admin"
    """Administrátor."""


class Permission(StrEnum):
    # Checked in a customer.
    CUSTOMER_READ = "customer.read"
    """See the dashboard, invoices, code lists, number series, parameters and files."""
    INVOICES_PROCESS = "invoices.process"
    """Upload, check, code, book and discard invoices; mark them paid; export."""
    CODELISTS_EDIT = "codelists.edit"
    """Import and edit code lists; edit parameters, conventions and number series."""
    TEMPLATES_USE = "templates.use"
    TEMPLATES_CREATE_CUSTOMER = "templates.create_customer"
    CUSTOMER_EDIT_CONTACT = "customer.edit_contact"
    """The customer's address and bank account."""
    CUSTOMER_EDIT_IDENTITY = "customer.edit_identity"
    """The customer's name, IČO and DIČ (plan §2 decision 50)."""
    CUSTOMER_ASSIGN_VARIABLE_NUMBER = "customer.assign_variable_number"
    LOGINS_MANAGE = "logins.manage"
    """Invite, deactivate and reactivate a customer's logins; send them a reset link."""
    CUSTOMERS_DELETE = "customers.delete"
    """Soft-delete, restore and purge a customer."""

    # Checked in a service provider (and by admins on the platform).
    TEMPLATES_CREATE_PROVIDER = "templates.create_provider"
    CUSTOMERS_CREATE = "customers.create"
    """Create a customer, new or as a copy: staff into their own provider."""
    PROVIDER_OVERVIEW = "provider.overview"
    """The provider's overview dashboard and its user list."""

    # Checked on the platform.
    TEMPLATES_CREATE_GLOBAL = "templates.create_global"
    PROVIDERS_MANAGE = "providers.manage"
    """Create and remove providers; add and remove staff; assign and unassign customers."""
    USERS_DELETE = "users.delete"
    """Soft-delete, restore and purge users."""
    USERS_ADMINISTER = "users.administer"
    """Lock and unlock users, force a logout, list every user."""
    USERS_IMPERSONATE = "users.impersonate"
    GLOBAL_CODELISTS = "codelists.global"
    AUDIT_READ = "audit.read"
    JOBS_MANAGE = "jobs.manage"
    OUTBOX_READ = "outbox.read"
    EVALUATION_READ = "evaluation.read"
    CUSTOMER_DATA_EXPORT = "customer.data_export"

    # The caller's own account.
    ACCOUNT_OWN = "account.own"
    """Edit one's own name, login email, notification email and password."""


ROLE_SCOPE: dict[Role, ScopeKind] = {
    Role.CUSTOMER_VIEWER: ScopeKind.CUSTOMER,
    Role.CUSTOMER_USER: ScopeKind.CUSTOMER,
    Role.PROVIDER_STAFF: ScopeKind.PROVIDER,
    Role.PLATFORM_ADMIN: ScopeKind.PLATFORM,
}

_VIEWER = frozenset({Permission.CUSTOMER_READ, Permission.ACCOUNT_OWN})

_USER = _VIEWER | {
    Permission.INVOICES_PROCESS,
    Permission.CODELISTS_EDIT,
    Permission.TEMPLATES_USE,
    Permission.TEMPLATES_CREATE_CUSTOMER,
    Permission.CUSTOMER_EDIT_CONTACT,
}

_STAFF = (_USER - {Permission.TEMPLATES_CREATE_CUSTOMER}) | {
    Permission.TEMPLATES_CREATE_PROVIDER,
    Permission.CUSTOMER_EDIT_IDENTITY,
    Permission.CUSTOMER_ASSIGN_VARIABLE_NUMBER,
    Permission.LOGINS_MANAGE,
    Permission.CUSTOMERS_CREATE,
    Permission.PROVIDER_OVERVIEW,
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.CUSTOMER_VIEWER: _VIEWER,
    Role.CUSTOMER_USER: frozenset(_USER),
    Role.PROVIDER_STAFF: frozenset(_STAFF),
    Role.PLATFORM_ADMIN: frozenset(Permission),
}
