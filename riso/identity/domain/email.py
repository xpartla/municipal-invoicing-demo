"""The `Email` value object: a login or notification address, normalised.

Normalising: surrounding whitespace is dropped and the whole address is lower-cased. The
local part is case-sensitive in theory, but no mail system people use treats it so, and two
logins differing only in case would be a trap. Unicode domains are checked through IDNA and
kept as typed.
"""

import re
from dataclasses import dataclass

from riso.shared.errors import ValidationFailed

MAX_LENGTH = 254
"""RFC 5321's limit on a forward path, less the angle brackets."""
MAX_LOCAL_LENGTH = 64

_LOCAL = re.compile(r"[^\s@\"(),:;<>\[\\\]]+")
_LABEL = re.compile(r"(?!-)[a-z0-9-]{1,63}(?<!-)")


def _domain_is_valid(domain: str) -> bool:
    try:
        ascii_domain = domain.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    labels = ascii_domain.split(".")
    return len(labels) >= 2 and all(_LABEL.fullmatch(label) for label in labels)


@dataclass(frozen=True, slots=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        if not _is_valid(self.value) or self.value != self.value.strip().lower():
            raise ValidationFailed.on("email", "not a valid email address", "email")

    @classmethod
    def parse(cls, text: str, field: str = "email") -> "Email":
        normalised = text.strip().lower()
        if not _is_valid(normalised):
            raise ValidationFailed.on(field, "not a valid email address", "email")
        return cls(normalised)

    @property
    def local_part(self) -> str:
        return self.value.rpartition("@")[0]

    def __str__(self) -> str:
        return self.value


def _is_valid(address: str) -> bool:
    if not address or len(address) > MAX_LENGTH or address.count("@") != 1:
        return False
    local, _, domain = address.partition("@")
    if not local or len(local) > MAX_LOCAL_LENGTH or not _LOCAL.fullmatch(local):
        return False
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False
    return _domain_is_valid(domain)
