"""The tenancy context: the accounting entities and who works on them: customers with their
profile, service providers and their customer assignments, and the customer's parameters
and coding conventions per year. Main aggregates: Customer, ServiceProvider. (Memberships
are identity's, with the roles they carry.) This module is the context's public surface:
other contexts import only what it exports (its application API), never its domain,
infrastructure or api modules. See plan §4.2 and guide §6.1."""

from riso.tenancy.application import (
    AddressInput,
    CreateCustomer,
    CustomerContact,
    CustomerIdentity,
    CustomerView,
    TenancyUnitOfWork,
    add_customer,
    copy_parameters,
    customer_directory,
    get_customer,
    list_providers,
)

__all__ = [
    "AddressInput",
    "CreateCustomer",
    "CustomerContact",
    "CustomerIdentity",
    "CustomerView",
    "TenancyUnitOfWork",
    "add_customer",
    "copy_parameters",
    "customer_directory",
    "get_customer",
    "list_providers",
]
