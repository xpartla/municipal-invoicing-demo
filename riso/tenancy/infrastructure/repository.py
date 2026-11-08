"""The tenancy repositories on SQLAlchemy, mapped explicitly."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from riso.shared.errors import NotFound
from riso.shared.uow import UnitOfWork
from riso.shared.values import Iban, Ico
from riso.tenancy.domain import (
    Address,
    Customer,
    CustomerParameters,
    CustomerStatus,
    ProviderStatus,
    ServiceProvider,
)
from riso.tenancy.infrastructure.orm import (
    CustomerParametersRow,
    CustomerRow,
    ProviderAssignmentRow,
    ServiceProviderRow,
)


class SqlCustomerRepository:
    def __init__(self, session: Session, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow

    def add(self, customer: Customer) -> None:
        row = CustomerRow(id=customer.id)
        _write_customer(customer, row)
        self._session.add(row)
        self._session.flush()  # the assignment row refers to it
        self._write_assignment(customer)
        self._uow.track(customer)

    def get(self, customer_id: str) -> Customer:
        row = self._session.get(CustomerRow, customer_id)
        if row is None:
            raise NotFound(f"no customer {customer_id}")
        return self._read(row)

    def find_active_by_ico(self, ico: Ico) -> Customer | None:
        row = self._session.scalars(
            select(CustomerRow).where(
                CustomerRow.ico == ico.value, CustomerRow.status == CustomerStatus.ACTIVE.value
            )
        ).first()
        return None if row is None else self._read(row)

    def save(self, customer: Customer) -> None:
        row = self._session.get(CustomerRow, customer.id)
        if row is None:
            raise NotFound(f"no customer {customer.id}")
        _write_customer(customer, row)
        self._write_assignment(customer)

    def remove(self, customer_id: str) -> None:
        self._session.execute(
            delete(ProviderAssignmentRow).where(ProviderAssignmentRow.customer_id == customer_id)
        )
        self._session.execute(delete(CustomerRow).where(CustomerRow.id == customer_id))

    def find(
        self, *, provider_id: str | None = None, include_deleted: bool = False
    ) -> list[Customer]:
        statement = select(CustomerRow)
        if provider_id is not None:
            statement = statement.join(
                ProviderAssignmentRow, ProviderAssignmentRow.customer_id == CustomerRow.id
            ).where(ProviderAssignmentRow.provider_id == provider_id)
        if not include_deleted:
            statement = statement.where(CustomerRow.status == CustomerStatus.ACTIVE.value)
        rows = self._session.scalars(statement.order_by(CustomerRow.name, CustomerRow.id)).all()
        return [self._read(row) for row in rows]

    def assigned_to(self, provider_id: str) -> list[Customer]:
        return self.find(provider_id=provider_id, include_deleted=True)

    def _read(self, row: CustomerRow) -> Customer:
        assignment = self._session.get(ProviderAssignmentRow, row.id)
        customer = Customer(
            id=row.id,
            name=row.name,
            ico=Ico(row.ico),
            created_at=row.created_at,
            dic=row.dic,
            address=(
                Address(row.street, row.city, row.postal_code, row.country)
                if row.street is not None
                and row.city is not None
                and row.postal_code is not None
                and row.country is not None
                else None
            ),
            iban=Iban(row.iban) if row.iban else None,
            variable_number=row.variable_number,
            provider_id=assignment.provider_id if assignment else None,
            status=CustomerStatus(row.status),
            deleted_at=row.deleted_at,
        )
        self._uow.track(customer)
        return customer

    def _write_assignment(self, customer: Customer) -> None:
        assignment = self._session.get(ProviderAssignmentRow, customer.id)
        if customer.provider_id is None:
            if assignment is not None:
                self._session.delete(assignment)
        elif assignment is None:
            self._session.add(
                ProviderAssignmentRow(customer_id=customer.id, provider_id=customer.provider_id)
            )
        else:
            assignment.provider_id = customer.provider_id


def _write_customer(customer: Customer, row: CustomerRow) -> None:
    row.name = customer.name
    row.ico = customer.ico.value
    row.dic = customer.dic
    address = customer.address
    row.street = address.street if address else None
    row.city = address.city if address else None
    row.postal_code = address.postal_code if address else None
    row.country = address.country if address else None
    row.iban = customer.iban.value if customer.iban else None
    row.variable_number = customer.variable_number
    row.status = customer.status.value
    row.created_at = customer.created_at
    row.deleted_at = customer.deleted_at


class SqlProviderRepository:
    def __init__(self, session: Session, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow

    def add(self, provider: ServiceProvider) -> None:
        row = ServiceProviderRow(id=provider.id)
        _write_provider(provider, row)
        self._session.add(row)
        self._uow.track(provider)

    def get(self, provider_id: str) -> ServiceProvider:
        row = self._session.get(ServiceProviderRow, provider_id)
        if row is None:
            raise NotFound(f"no provider {provider_id}")
        return self._read(row)

    def save(self, provider: ServiceProvider) -> None:
        row = self._session.get(ServiceProviderRow, provider.id)
        if row is None:
            raise NotFound(f"no provider {provider.id}")
        _write_provider(provider, row)

    def find(self, *, include_removed: bool = False) -> list[ServiceProvider]:
        statement = select(ServiceProviderRow)
        if not include_removed:
            statement = statement.where(ServiceProviderRow.status == ProviderStatus.ACTIVE.value)
        rows = self._session.scalars(
            statement.order_by(ServiceProviderRow.name, ServiceProviderRow.id)
        ).all()
        return [self._read(row) for row in rows]

    def _read(self, row: ServiceProviderRow) -> ServiceProvider:
        provider = ServiceProvider(
            id=row.id,
            name=row.name,
            created_at=row.created_at,
            ico=Ico(row.ico) if row.ico else None,
            status=ProviderStatus(row.status),
            removed_at=row.removed_at,
        )
        self._uow.track(provider)
        return provider


def _write_provider(provider: ServiceProvider, row: ServiceProviderRow) -> None:
    row.name = provider.name
    row.ico = provider.ico.value if provider.ico else None
    row.status = provider.status.value
    row.created_at = provider.created_at
    row.removed_at = provider.removed_at


class SqlParametersRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, customer_id: str, year: int) -> CustomerParameters | None:
        row = self._session.get(CustomerParametersRow, (customer_id, year))
        if row is None:
            return None
        return CustomerParameters(
            customer_id=row.customer_id,
            year=row.year,
            vat_payer=row.vat_payer,
            reference_period=row.reference_period,
            default_zdroj=row.default_zdroj,
            default_series=row.default_series,
            default_dal=row.default_dal,
            canteen_series=row.canteen_series,
            canteen_dal=row.canteen_dal,
        )

    def save(self, parameters: CustomerParameters) -> None:
        row = self._session.get(CustomerParametersRow, (parameters.customer_id, parameters.year))
        if row is None:
            row = CustomerParametersRow(customer_id=parameters.customer_id, year=parameters.year)
            self._session.add(row)
        for name, value in parameters.values().items():
            setattr(row, name, value)

    def years(self, customer_id: str) -> list[int]:
        return list(
            self._session.scalars(
                select(CustomerParametersRow.year)
                .where(CustomerParametersRow.customer_id == customer_id)
                .order_by(CustomerParametersRow.year)
            )
        )

    def remove_all(self, customer_id: str) -> None:
        self._session.execute(
            delete(CustomerParametersRow).where(CustomerParametersRow.customer_id == customer_id)
        )
