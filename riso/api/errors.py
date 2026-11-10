"""Mapping the domain errors to HTTP (guide §6.5).

| Error | Status | Body |
|---|---|---|
| `Unauthenticated` | 401 | `{"detail": message, "code": "unauthenticated"}` |
| `NotFound` | 404 | `{"detail": message, "code": "not_found"}` |
| `PermissionDenied` | 403 | `{"detail": message, "code": "permission_denied"}` |
| `Conflict` | 409 | `{"detail": message, "code": "conflict"}` |
| `InvalidState` | 409 | `{"detail": message, "code": "invalid_state"}` |
| `ValidationFailed` | 422 | `{"detail": [{"loc", "msg", "type"}…], "code": "validation_failed"}` |
| `Throttled` | 429 | `{"detail": message, "code": "throttled", "retry_after": s}`, `Retry-After` |
| anything else | 500 | `{"detail": "Internal Server Error", "request_id": …}` |

The 422 body has the shape of FastAPI's own request validation errors, so the frontend maps
both onto form fields the same way: `loc` is `["body", *field.split(".")]`, with list indices
as numbers.

A customer the caller cannot access is reported as `NotFound` by the access check (P2-M1),
so its existence does not leak.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from riso.shared.errors import (
    Conflict,
    DomainError,
    InvalidState,
    NotFound,
    PermissionDenied,
    Throttled,
    Unauthenticated,
    ValidationFailed,
)

log = logging.getLogger(__name__)

_STATUS: list[tuple[type[DomainError], int, str]] = [
    (Unauthenticated, 401, "unauthenticated"),
    (NotFound, 404, "not_found"),
    (PermissionDenied, 403, "permission_denied"),
    (Conflict, 409, "conflict"),
    (InvalidState, 409, "invalid_state"),
]


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unexpected)


async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
    if isinstance(exc, ValidationFailed):
        return JSONResponse(
            {"detail": validation_detail(exc), "code": "validation_failed"}, status_code=422
        )
    if isinstance(exc, Throttled):
        return JSONResponse(
            {"detail": exc.message, "code": "throttled", "retry_after": exc.retry_after},
            status_code=429,
            headers={"Retry-After": str(exc.retry_after)},
        )
    for kind, status, code in _STATUS:
        if isinstance(exc, kind):
            body = {"detail": exc.message, "code": exc.code or code, **exc.details()}
            return JSONResponse(body, status_code=status)
    return await _unexpected(request, exc)


def validation_detail(exc: ValidationFailed) -> list[dict[str, object]]:
    if not exc.errors:
        return [{"loc": ["body"], "msg": exc.message, "type": "validation_failed"}]
    return [
        {"loc": ["body", *_loc(error.field)], "msg": error.message, "type": error.code}
        for error in exc.errors
    ]


def _loc(field: str) -> list[str | int]:
    return [int(part) if part.isdigit() else part for part in field.split(".") if part]


async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    log.exception("unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
    return JSONResponse(
        {"detail": "Internal Server Error", "request_id": request_id}, status_code=500
    )
