"""Document numbers in a series pattern such as 'FD/XXX/RR': a run of X is the zero-padded
sequence, RR the two-digit year, MM the month."""

import re
from dataclasses import dataclass

_TOKENS = re.compile(r"(X+|RR|MM)")


@dataclass(frozen=True)
class ParsedNumber:
    sequence: int
    year: int | None
    month: int | None


def format_number(pattern: str, sequence: int, year: int, month: int | None = None) -> str:
    """format_number('FD/XXX/RR', 144, 2026) == 'FD/144/26'."""
    out = []
    for part in _TOKENS.split(pattern):
        if part.startswith("X"):
            out.append(str(sequence).zfill(len(part)))
        elif part == "RR":
            out.append(f"{year % 100:02d}")
        elif part == "MM":
            if month is None:
                raise ValueError(f"pattern {pattern!r} needs a month")
            out.append(f"{month:02d}")
        else:
            out.append(part)
    return "".join(out)


def parse_number(pattern: str, number: str) -> ParsedNumber | None:
    """The parts of a number written in the pattern, or None when it does not fit."""
    regex = []
    for part in _TOKENS.split(pattern):
        if part.startswith("X"):
            regex.append(rf"(?P<sequence>\d{{{len(part)},}})")
        elif part == "RR":
            regex.append(r"(?P<year>\d{2})")
        elif part == "MM":
            regex.append(r"(?P<month>\d{2})")
        else:
            regex.append(re.escape(part))
    match = re.fullmatch("".join(regex), number)
    if match is None:
        return None
    parts = match.groupdict()
    return ParsedNumber(
        sequence=int(parts["sequence"]),
        year=int(parts["year"]) if parts.get("year") else None,
        month=int(parts["month"]) if parts.get("month") else None,
    )
