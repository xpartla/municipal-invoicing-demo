"""Errors the domain and the use cases raise. The API maps them to HTTP (guide §6.5):
`Unauthenticated` 401, `NotFound` 404, `PermissionDenied` 403, `Conflict` and `InvalidState`
409, `ValidationFailed` 422 with field errors, `Throttled` 429 with `Retry-After`.

Messages carry IDs and states, never invoice content, names or IBANs, because they end up in
logs.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")


class DomainError(Exception):
    """Base of the errors the API knows how to map."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Unauthenticated(DomainError):
    """No valid session, or a login that failed. Says nothing about which part was wrong."""


class Throttled(DomainError):
    """Too many failed attempts; try again after `retry_after` seconds."""

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = max(1, retry_after)


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

    @classmethod
    def from_pydantic(
        cls, message: str, errors: list[Any], *, prefix: str = ""
    ) -> "ValidationFailed":
        """From the `errors()` of a Pydantic `ValidationError`: each `loc` becomes a dotted
        field, under `prefix` when given."""
        found = []
        for error in errors:
            parts = [str(part) for part in error.get("loc", ())]
            name = ".".join([prefix, *parts] if prefix else parts)
            found.append(FieldError(name, str(error.get("msg", "")), str(error.get("type", ""))))
        return cls(message, found)


class FieldErrors:
    """Collects the failures of several fields, so a form gets all of them at once.

    errors = FieldErrors()
    ico = errors.check(lambda: Ico.parse(cmd.ico))
    iban = errors.check(lambda: Iban.parse(cmd.iban)) if cmd.iban else None
    errors.raise_if_any("invalid customer")
    """

    def __init__(self) -> None:
        self.errors: list[FieldError] = []

    def check(self, parse: Callable[[], T]) -> T | None:
        try:
            return parse()
        except ValidationFailed as exc:
            self.errors.extend(exc.errors or [FieldError("", exc.message, "invalid")])
            return None

    def raise_if_any(self, message: str) -> None:
        if self.errors:
            raise ValidationFailed(message, list(self.errors))
