"""Field types and the base model shared by every contract."""

from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    WithJsonSchema,
)


class Contract(BaseModel):
    """Base of every JSON contract. Unknown fields are rejected, so a typo in a data file
    fails loudly instead of being dropped."""

    model_config = ConfigDict(extra="forbid")


def _decimal_from_json(value: object) -> object:
    # JSON numbers arrive as floats; going through str keeps 93.71 from becoming 93.7099...
    if isinstance(value, float):
        return Decimal(str(value))
    return value


_AS_JSON_NUMBER = PlainSerializer(float, return_type=float, when_used="json")

# An amount as printed on the invoice, at any precision: Telekom prints net amounts to four places.
Amount = Annotated[
    Decimal,
    BeforeValidator(_decimal_from_json),
    _AS_JSON_NUMBER,
    WithJsonSchema({"type": "number", "description": "EUR, as printed on the invoice"}),
]

# An amount as entered into the accounting software.
BookingAmount = Annotated[
    Decimal,
    BeforeValidator(_decimal_from_json),
    Field(decimal_places=2),
    _AS_JSON_NUMBER,
    WithJsonSchema({"type": "number", "description": "EUR, at most two decimals"}),
]

Ico = Annotated[str, StringConstraints(pattern=r"^\d{8}$")]
Period = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]

# Synthetic and analytic account, joined in the software's format as 'SU AU', e.g. '518 001'.
Su = Annotated[str, StringConstraints(pattern=r"^\d{3}$")]
Au = Annotated[str, StringConstraints(pattern=r"^\d{3}$")]
AccountKey = Annotated[str, StringConstraints(pattern=r"^\d{3} \d{3}$")]

# The five parts of a budget position, joined as 'EK zdroj oddiel trieda analytika',
# e.g. '637005 41 01 110 000'. Zdroj codes look like 41, 111, 11H, 72f or 1AD1.
Ek = Annotated[str, StringConstraints(pattern=r"^\d{6}$")]
Zdroj = Annotated[str, StringConstraints(pattern=r"^\d[0-9A-Za-z]{1,3}$")]
Oddiel = Annotated[str, StringConstraints(pattern=r"^\d{2}$")]
Trieda = Annotated[str, StringConstraints(pattern=r"^\d{3}$")]
Analytika = Annotated[str, StringConstraints(pattern=r"^\d{3}$")]
BudgetKey = Annotated[
    str, StringConstraints(pattern=r"^\d{6} \d[0-9A-Za-z]{1,3} \d{2} \d{3} \d{3}$")
]
