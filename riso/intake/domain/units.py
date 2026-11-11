"""Units of measure on e-invoices (plan §8.4, decision 65). UBL writes them as UN/ECE
Recommendation 20 codes (Recommendation 21 packaging codes with an `X` in front), Slovak
invoices print the abbreviations. A code maps to the abbreviation a Slovak invoice prints; an
abbreviation without a code of its own (`výsyp`, `obd.`) is written as `C62`, "one", and
reads back as `ks`. A code missing from the table is kept as written.
"""

CODE_OF_UNIT: dict[str, str] = {
    "ks": "C62",
    "kWh": "KWH",
    "MWh": "MWH",
    "mes.": "MON",
    "rok": "ANN",
    "deň": "DAY",
    "týž.": "WEE",
    "hod": "HUR",
    "min": "MIN",
    "kg": "KGM",
    "g": "GRM",
    "t": "TNE",
    "l": "LTR",
    "m": "MTR",
    "km": "KMT",
    "m²": "MTK",
    "m³": "MTQ",
    "ha": "HAR",
    "kpl": "SET",
    "pár": "PR",
    "os.": "IE",
    "bal": "XPK",
    "kart": "XCT",
}
"""A Slovak abbreviation to its code."""

ONE = "C62"

UNIT_OF_CODE: dict[str, str] = {code: unit for unit, code in CODE_OF_UNIT.items()} | {
    "H87": "ks",
    "EA": "ks",
    "XPA": "bal",
    "XBX": "kart",
}
"""A code to the Slovak abbreviation; `C62` and `H87` (a piece) both read as `ks`."""


def code_of(unit: str) -> str:
    """The code a Slovak abbreviation is written with; `C62` when it has none."""
    return CODE_OF_UNIT.get(unit, ONE)


def unit_of(code: str) -> str:
    """The abbreviation a code reads as; the code itself when the table has none."""
    return UNIT_OF_CODE.get(code.strip(), code.strip())
