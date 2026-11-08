"""A customer's parameters for one year (plan §6.4): today's `EntityContext` without the IČO
and the name, which come from the customer.

The parameters validate through the `EntityContext` contract itself, so their rules are
exactly the contract's (zdroj, account keys and the period by their patterns). M2 replaces
`reference_period` with the code list versions of the year.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from pydantic import ValidationError

from riso.contracts import EntityContext
from riso.shared.errors import FieldError, ValidationFailed

MIN_YEAR, MAX_YEAR = 2000, 2100
_PLACEHOLDER = {"ico": "00000000", "name": "-"}
"""Stands in for the customer's own IČO and name while the parameters are checked alone."""


@dataclass(frozen=True, slots=True)
class CustomerParameters:
    customer_id: str
    year: int
    vat_payer: bool
    reference_period: str
    default_zdroj: str
    default_series: str
    default_dal: str
    canteen_series: str
    canteen_dal: str

    FIELDS = (
        "vat_payer",
        "reference_period",
        "default_zdroj",
        "default_series",
        "default_dal",
        "canteen_series",
        "canteen_dal",
    )

    @classmethod
    def parse(cls, customer_id: str, year: int, values: Mapping[str, Any]) -> "CustomerParameters":
        """Validates `values` (the fields above) as `EntityContext` does, and the year."""
        if not MIN_YEAR <= year <= MAX_YEAR:
            raise ValidationFailed.on("year", f"between {MIN_YEAR} and {MAX_YEAR}", "year")
        unknown = sorted(set(values) - set(cls.FIELDS))
        if unknown:
            raise ValidationFailed(
                "invalid parameters",
                [FieldError(name, "not a parameter", "extra_forbidden") for name in unknown],
            )
        try:
            context = EntityContext.model_validate({**_PLACEHOLDER, "budget_year": year, **values})
        except ValidationError as exc:
            raise ValidationFailed.from_pydantic("invalid parameters", exc.errors()) from exc
        return cls(
            customer_id=customer_id,
            year=year,
            **{name: getattr(context, name) for name in cls.FIELDS},
        )

    def values(self) -> dict[str, Any]:
        """The fields without the customer and the year."""
        data = asdict(self)
        return {name: data[name] for name in self.FIELDS}

    def entity_context(self, *, ico: str, name: str) -> EntityContext:
        """What the engine reads."""
        return EntityContext.model_validate(
            {"ico": ico, "name": name, "budget_year": self.year, **self.values()}
        )
