"""Errors the domain and the use cases raise. The API maps them to HTTP (guide §6.5):
`NotFound` 404, `PermissionDenied` 403, `Conflict` and `InvalidState` 409, `ValidationFailed`
422 with field errors.

Messages carry IDs and states, never invoice content, names or IBANs, because they end up in
logs.
"""

from dataclasses import dataclass


class DomainError(Exception):
    """Base of the errors the API knows how to map."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    """The thing does not exist, or the caller may not know it exists."""


class PermissionDenied(DomainError):
    """The caller lacks a permission inside a scope it can see."""


class Conflict(DomainError):
    """The request clashes with existing data, e.g. a duplicate IČO or a used number."""


class InvalidState(DomainError):
    """The transition is not allowed from the current state."""


@dataclass(frozen=True, slots=True)
class FieldError:
    """One invalid input field. `field` is a dotted path (`address.city`, `lines.0.amount`)."""

    field: str
    message: str
    code: str = "invalid"


class ValidationFailed(DomainError):
    """The input breaks a rule; `errors` says which fields."""

    def __init__(self, message: str, errors: list[FieldError] | None = None) -> None:
        super().__init__(message)
        self.errors: list[FieldError] = list(errors or [])

    @classmethod
    def on(cls, field: str, message: str, code: str = "invalid") -> "ValidationFailed":
        """A failure of one field."""
        return cls(message, [FieldError(field, message, code)])
