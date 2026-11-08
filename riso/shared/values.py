"""Value objects used across contexts: IČO, IBAN and money.

They validate in their constructors and raise `ValidationFailed`, naming the field `ico`,
`iban` or `amount`; a caller with a different field name passes it to `parse`.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from riso.shared.errors import ValidationFailed

CENT = Decimal("0.01")


def ico_is_valid(ico: str) -> bool:
    """The check digit of an 8-digit IČO: weights 8 to 2, then (11 - sum mod 11) mod 10.
    Anything that is not eight digits is invalid."""
    if len(ico) != 8 or not ico.isdigit():
        return False
    digits = [int(c) for c in ico]
    total = sum(weight * digit for weight, digit in zip(range(8, 1, -1), digits[:7], strict=True))
    return (11 - total % 11) % 10 == digits[7]


@dataclass(frozen=True, slots=True)
class Ico:
    """An organisation's identification number (IČO): eight digits with a check digit."""

    value: str

    def __post_init__(self) -> None:
        if not ico_is_valid(self.value):
            raise ValidationFailed.on("ico", "not a valid IČO", "ico_check_digit")

    @classmethod
    def parse(cls, text: str, field: str = "ico") -> "Ico":
        """Reads an IČO as people type it: spaces are dropped and the old six- and seven-digit
        numbers get their leading zeros back."""
        digits = "".join(text.split())
        if digits.isdigit() and 6 <= len(digits) <= 8:
            digits = digits.zfill(8)
        if not ico_is_valid(digits):
            raise ValidationFailed.on(field, "not a valid IČO", "ico_check_digit")
        return cls(digits)

    def __str__(self) -> str:
        return self.value


# IBAN lengths of the countries Slovak municipalities usually pay into; other countries are
# checked by the generic shape and the mod-97 check only.
_IBAN_LENGTHS = {"SK": 24, "CZ": 24, "AT": 20, "HU": 28, "PL": 28, "DE": 22}
_IBAN_SHAPE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")


def iban_is_valid(iban: str) -> bool:
    """The shape, the known country length and the ISO 13616 mod-97 check of a compact IBAN."""
    if not _IBAN_SHAPE.match(iban):
        return False
    expected = _IBAN_LENGTHS.get(iban[:2])
    if expected is not None and len(iban) != expected:
        return False
    rearranged = iban[4:] + iban[:4]
    number = "".join(str(int(c, 36)) for c in rearranged)
    return int(number) % 97 == 1


@dataclass(frozen=True, slots=True)
class Iban:
    """A bank account number, kept compact (no spaces, upper case)."""

    value: str

    def __post_init__(self) -> None:
        if not iban_is_valid(self.value):
            raise ValidationFailed.on("iban", "not a valid IBAN", "iban_check")

    @classmethod
    def parse(cls, text: str, field: str = "iban") -> "Iban":
        compact = "".join(text.split()).upper()
        if not iban_is_valid(compact):
            raise ValidationFailed.on(field, "not a valid IBAN", "iban_check")
        return cls(compact)

    @property
    def formatted(self) -> str:
        """In groups of four, as printed on invoices: `SK31 1200 0000 …`."""
        return " ".join(self.value[i : i + 4] for i in range(0, len(self.value), 4))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Money:
    """An amount in a currency, exact to the cent. The database stores it as integer cents."""

    amount: Decimal
    currency: str = "EUR"

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal) or not self.amount.is_finite():
            raise ValidationFailed.on("amount", "not a finite decimal amount", "amount")
        try:
            exact = self.amount.quantize(CENT)
        except InvalidOperation as exc:
            raise ValidationFailed.on("amount", "amount out of range", "amount") from exc
        if exact != self.amount:
            raise ValidationFailed.on("amount", "more than two decimal places", "amount_precision")
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValidationFailed.on("currency", "not an ISO 4217 code", "currency")
        object.__setattr__(self, "amount", exact)

    @property
    def cents(self) -> int:
        return int(self.amount.scaleb(2))

    @classmethod
    def from_cents(cls, cents: int, currency: str = "EUR") -> "Money":
        return cls(Decimal(cents).scaleb(-2).quantize(CENT), currency)

    def __add__(self, other: "Money") -> "Money":
        self._same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def _same_currency(self, other: "Money") -> None:
        if other.currency != self.currency:
            raise ValidationFailed.on("currency", "currencies differ", "currency_mismatch")

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"
