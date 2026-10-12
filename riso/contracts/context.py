"""EntityContext: per-municipality settings the exports do not carry (plan section 3.3)."""

from pydantic import Field

from riso.contracts.base import AccountKey, Contract, Ico, Period, Zdroj


class EntityContext(Contract):
    ico: Ico
    name: str
    vat_payer: bool = Field(description="When false, the gross is booked as one amount")
    budget_year: int
    reference_period: Period = Field(description="Period of the bundle the engine reads")
    default_zdroj: Zdroj
    default_series: str
    default_dal: AccountKey
    canteen_series: str
    canteen_dal: AccountKey
