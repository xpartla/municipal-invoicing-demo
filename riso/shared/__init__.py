"""The shared kernel: IDs, the clock, base errors, domain events, the request context, the
unit-of-work protocol, and value objects used everywhere. Pure Python: no I/O, no
SQLAlchemy, no FastAPI; the domain packages and the engine may import it."""

from riso.shared.clock import BRATISLAVA, Clock, FixedClock, SystemClock, local_date
from riso.shared.context import AccessPolicy, AllowAll, DenyAll, RequestContext
from riso.shared.errors import (
    Conflict,
    DomainError,
    FieldError,
    FieldErrors,
    InvalidState,
    NotFound,
    PermissionDenied,
    Throttled,
    Unauthenticated,
    ValidationFailed,
)
from riso.shared.events import DomainEvent, EventDispatcher, HasEvents
from riso.shared.ids import IdGenerator, UuidV7Generator, new_id, uuid7_time
from riso.shared.uow import UnitOfWork
from riso.shared.values import Iban, Ico, Money, clean_name, iban_is_valid, ico_is_valid

__all__ = [
    "BRATISLAVA",
    "AccessPolicy",
    "AllowAll",
    "Clock",
    "Conflict",
    "DenyAll",
    "DomainError",
    "DomainEvent",
    "EventDispatcher",
    "FieldError",
    "FieldErrors",
    "FixedClock",
    "HasEvents",
    "Iban",
    "Ico",
    "IdGenerator",
    "InvalidState",
    "Money",
    "NotFound",
    "PermissionDenied",
    "RequestContext",
    "SystemClock",
    "Throttled",
    "Unauthenticated",
    "UnitOfWork",
    "UuidV7Generator",
    "ValidationFailed",
    "clean_name",
    "iban_is_valid",
    "ico_is_valid",
    "local_date",
    "new_id",
    "uuid7_time",
]
