"""ASGI middleware: the request ID, and the security headers (plan §12).

Both are plain ASGI, not `BaseHTTPMiddleware`, so the request ID's context variable reaches
the endpoints, including the sync ones that run in the thread pool.
"""

import re
from collections.abc import Callable
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from riso.platform.log import request_id_var
from riso.shared.ids import new_id

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_BASE = {
    "default-src": "'self'",
    "script-src": "'self'",
    # Mantine writes its CSS variables in a <style> element and some style attributes.
    "style-src": "'self' 'unsafe-inline'",
    "img-src": "'self' data: blob:",
    "font-src": "'self' data:",
    "connect-src": "'self'",
    "object-src": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
    "frame-ancestors": "'none'",
}


def _policy(**overrides: str) -> str:
    return "; ".join(f"{k} {v}" for k, v in {**_BASE, **overrides}.items())


CSP_STRICT = _policy()
"""The SPA and the API: no inline or evaluated scripts."""
CSP_LEGACY = _policy(**{"script-src": "'self' 'unsafe-eval'"})
"""The demo's Alpine.js pages, until P2-M4 removes them: Alpine evaluates its attributes."""
CSP_DOCS = _policy(
    **{
        "script-src": "'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "style-src": "'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "img-src": "'self' data: https://fastapi.tiangolo.com",
    }
)
"""FastAPI's /docs and /redoc pages, which load Swagger UI and ReDoc from a CDN."""

DOCS_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc"})
CSP_STATE_KEY = "riso_csp"
"""Set in `scope["state"]` by the app that served the response, to pick its policy."""

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=(), payment=()",
}


class RequestIdMiddleware:
    """Takes a well-formed `X-Request-ID` from the client or makes one, keeps it in
    `scope["state"]["request_id"]` and the logging context, and returns it as a header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = _header(scope, b"x-request-id")
        request_id = incoming if incoming and _VALID_REQUEST_ID.match(incoming) else new_id()
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_var.reset(token)


class SecurityHeadersMiddleware:
    """Adds the security headers and the Content-Security-Policy to every response, and
    `Cache-Control: no-store` to API responses that set no caching of their own."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        state: dict[str, Any] = scope.setdefault("state", {})

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if path in DOCS_PATHS:
                    policy = CSP_DOCS
                elif state.get(CSP_STATE_KEY) == "legacy":
                    policy = CSP_LEGACY
                else:
                    policy = CSP_STRICT
                headers.setdefault("Content-Security-Policy", policy)
                if path == "/api" or path.startswith("/api/"):
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", ()):
        if key == name:
            return str(value.decode("latin-1"))
    return None


class CsrfCookieMiddleware:
    """Gives a caller without a `riso_csrf` cookie a random one, so even the requests before
    a login (the login itself, a password reset) carry a double-submit token. A response that
    sets the cookie itself (login, logout) is left alone."""

    def __init__(self, app: ASGIApp, *, new_token: Callable[[], str], secure: bool = False) -> None:
        self.app = app
        self._new_token = new_token
        self._secure = secure

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or _has_cookie(scope, CSRF_COOKIE_NAME):
            await self.app(scope, receive, send)
            return

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                prefix = f"{CSRF_COOKIE_NAME}="
                if not any(v.startswith(prefix) for v in headers.getlist("set-cookie")):
                    cookie = f"{prefix}{self._new_token()}; Path=/; SameSite=lax"
                    headers.append("set-cookie", cookie + ("; Secure" if self._secure else ""))
            await send(message)

        await self.app(scope, receive, send_with_cookie)


CSRF_COOKIE_NAME = "riso_csrf"


def _has_cookie(scope: Scope, name: str) -> bool:
    for key, value in scope.get("headers", ()):
        if key == b"cookie":
            for part in value.decode("latin-1").split(";"):
                if part.strip().startswith(f"{name}="):
                    return True
    return False
