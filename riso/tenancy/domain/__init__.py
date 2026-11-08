"""Entities, value objects, domain services, events, repository protocols and errors of the tenancy
context. Pure Python: it imports only this context's domain, `riso.shared` and `riso.contracts`;
never SQLAlchemy, FastAPI, `riso.platform` or I/O libraries."""

from riso.tenancy.domain.customer import (
    Address,
    Customer,
    CustomerStatus,
    parse_dic,
    parse_variable_number,
)
from riso.tenancy.domain.parameters import CustomerParameters
from riso.tenancy.domain.provider import ProviderStatus, ServiceProvider
from riso.tenancy.domain.repository import (
    CustomerRepository,
    ParametersRepository,
    ProviderRepository,
)

__all__ = [
    "Address",
    "Customer",
    "CustomerParameters",
    "CustomerRepository",
    "CustomerStatus",
    "ParametersRepository",
    "ProviderRepository",
    "ProviderStatus",
    "ServiceProvider",
    "parse_dic",
    "parse_variable_number",
]
