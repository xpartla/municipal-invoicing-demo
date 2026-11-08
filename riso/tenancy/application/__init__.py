"""Use cases (commands and queries), views (DTOs) and ports of the tenancy context. A use case
checks its permission first, runs in one unit of work, and returns views, never entities or ORM
objects."""

from riso.tenancy.application.customers import (
    AddressInput,
    CreateCustomer,
    CustomerContact,
    CustomerIdentity,
    TenancyUnitOfWork,
    assign_variable_number,
    create_customer,
    delete_customer,
    get_customer,
    get_parameters,
    restore_customer,
    set_parameters,
    update_contact,
    update_identity,
)
from riso.tenancy.application.providers import ProviderOverview, get_provider
from riso.tenancy.application.views import (
    AddressView,
    CustomerView,
    ParametersView,
    ProviderView,
)

__all__ = [
    "AddressInput",
    "AddressView",
    "CreateCustomer",
    "CustomerContact",
    "CustomerIdentity",
    "CustomerView",
    "ParametersView",
    "ProviderOverview",
    "ProviderView",
    "TenancyUnitOfWork",
    "assign_variable_number",
    "create_customer",
    "delete_customer",
    "get_customer",
    "get_parameters",
    "get_provider",
    "restore_customer",
    "set_parameters",
    "update_contact",
    "update_identity",
]
