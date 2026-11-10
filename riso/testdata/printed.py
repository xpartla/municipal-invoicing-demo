"""How values are printed on Slovak invoices: decimal comma, grouped thousands, dates with
dots, IBANs in groups of four. Each style is one way real invoices do it."""

import datetime as dt
from decimal import Decimal
from typing import Literal

NBSP = " "

DateStyle = Literal["dd.mm.yyyy", "d.m.yyyy", "d. m. yyyy"]
DATE_STYLES: tuple[DateStyle, ...] = ("dd.mm.yyyy", "d.m.yyyy", "d. m. yyyy")


def amount(value: Decimal, *, thousands: str = NBSP, decimals: int = 2) -> str:
    """`1234.5` → `1 234,50` (with a no-break space). More decimals are kept when the value has
    them, as unit prices do (`0,1389`), up to four."""
    exponent = value.normalize().as_tuple().exponent
    places = max(decimals, min(4, -exponent)) if isinstance(exponent, int) else decimals
    text = f"{abs(value):.{places}f}"
    whole, _, fraction = text.partition(".")
    groups: list[str] = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    sign = "-" if value < 0 else ""
    return f"{sign}{thousands.join(groups)},{fraction}"


def quantity(value: Decimal) -> str:
    """Quantities without trailing zeros: `1240`, `1,5`."""
    text = format(value.normalize(), "f")
    return text.replace(".", ",")


def money(value: Decimal, currency: str, *, thousands: str = NBSP) -> str:
    return f"{amount(value, thousands=thousands)}{NBSP}{currency}"


def date(value: dt.date, style: DateStyle) -> str:
    if style == "dd.mm.yyyy":
        return f"{value.day:02d}.{value.month:02d}.{value.year}"
    if style == "d.m.yyyy":
        return f"{value.day}.{value.month}.{value.year}"
    return f"{value.day}. {value.month}. {value.year}"


def iban(value: str, *, grouped: bool) -> str:
    compact = "".join(value.split()).upper()
    if not grouped:
        return compact
    return " ".join(compact[i : i + 4] for i in range(0, len(compact), 4))


def ico(value: str, *, spaced: bool) -> str:
    """`35823551` or, as some registries print it, `35 823 551`."""
    digits = "".join(value.split())
    if not spaced or len(digits) != 8:
        return digits
    return f"{digits[:2]} {digits[2:5]} {digits[5:]}"


def percent(value: Decimal) -> str:
    return f"{quantity(value)}{NBSP}%"
