"""The password policy and the hashing port (plan §5.3).

A password needs at least 12 characters, at most 256, and must not be on the list of common
passwords, nor be the account's own email address or name. The list is data: the policy
receives it (the infrastructure loads the bundled list), so the domain does no I/O.
Comparisons with the list ignore case.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from riso.shared.errors import FieldError, ValidationFailed

MIN_LENGTH = 12
MAX_LENGTH = 256
"""Long enough for any passphrase, short enough that hashing it costs nothing extra."""


@dataclass(frozen=True, slots=True)
class PasswordPolicy:
    common: frozenset[str] = field(default_factory=frozenset)
    """Common passwords, case-folded."""
    min_length: int = MIN_LENGTH
    max_length: int = MAX_LENGTH

    def problems(self, password: str, *, account: Iterable[str] = ()) -> list[str]:
        """The rules `password` breaks, as codes. `account` holds words of the account (its
        email, the email's local part, the name) the password must not equal."""
        if len(password) < self.min_length:
            return ["password_too_short"]
        if len(password) > self.max_length:
            return ["password_too_long"]
        folded = password.casefold()
        found = []
        if folded in self.common or folded.strip() in self.common:
            found.append("password_common")
        if any(folded == word.casefold() for word in account if word):
            found.append("password_like_account")
        if len(set(password)) < 3:
            found.append("password_common")  # "aaaaaaaaaaaa", "abababababab"
        return sorted(set(found))

    def check(self, password: str, *, field: str = "password", account: Iterable[str] = ()) -> None:
        """Raises `ValidationFailed` on `field` when the password breaks a rule."""
        codes = self.problems(password, account=account)
        if codes:
            raise ValidationFailed(
                "the password does not meet the policy",
                [FieldError(field, _MESSAGES[code], code) for code in codes],
            )


_MESSAGES = {
    "password_too_short": f"at least {MIN_LENGTH} characters",
    "password_too_long": f"at most {MAX_LENGTH} characters",
    "password_common": "too common or too simple",
    "password_like_account": "must differ from the email address and the name",
}


class PasswordHasher(Protocol):
    """Hashes passwords for storage (argon2id in `riso.identity.infrastructure.hashing`)."""

    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool:
        """Whether `password` matches; False for a malformed hash, never an exception."""
        ...

    def needs_rehash(self, password_hash: str) -> bool:
        """Whether the hash was made with weaker parameters than the current ones."""
        ...
