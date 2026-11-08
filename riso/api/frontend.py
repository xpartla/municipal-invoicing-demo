"""Serving the pages: the built SPA and, until P2-M4, the demo's Alpine pages.

This app is the router's default, so it runs only when no API route matched; API paths that
match no route get a JSON 404 here instead of a page.

- Without a built SPA (no `index.html` in `spa_dir`): the demo pages exactly as before, with
  `/` the invoice picker.
- With one: `/` and every path without a file extension (a client route such as
  `/c/123/invoices`) get the SPA's `index.html`; existing demo files keep their paths, so the
  picker is at `/index.html`; the SPA's own files (`/assets/…`) are served from `spa_dir`,
  hashed assets with a year's caching.
"""

import stat
from pathlib import Path, PurePosixPath

from starlette.datastructures import MutableHeaders
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Message, Receive, Scope, Send

from riso.api.middleware import CSP_STATE_KEY

_IMMUTABLE = "public, max-age=31536000, immutable"


class FrontendFiles:
    def __init__(self, legacy_dir: Path, spa_dir: Path | None = None) -> None:
        self._legacy = StaticFiles(directory=legacy_dir, html=True)
        self._spa_index = spa_dir / "index.html" if spa_dir else None
        self._spa: StaticFiles | None = None
        if spa_dir is not None and self._spa_index is not None and self._spa_index.is_file():
            self._spa = StaticFiles(directory=spa_dir)

    @property
    def serves_spa(self) -> bool:
        return self._spa is not None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        path: str = scope["path"]
        if path == "/api" or path.startswith("/api/"):
            await JSONResponse({"detail": "Not Found"}, status_code=404)(scope, receive, send)
            return
        if scope["method"] not in ("GET", "HEAD"):
            await PlainTextResponse("Method Not Allowed", status_code=405)(scope, receive, send)
            return
        if self._spa is None:
            await self._serve_legacy(scope, receive, send)
            return
        if path == "/":
            await self._index()(scope, receive, send)
            return
        relative = path.lstrip("/")
        if self._exists(self._legacy, relative):
            await self._serve_legacy(scope, receive, send)
        elif self._exists(self._spa, relative):
            await self._serve_spa_file(scope, receive, send)
        elif "." not in PurePosixPath(path).name:
            await self._index()(scope, receive, send)
        else:
            await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)

    async def _serve_legacy(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope.setdefault("state", {})[CSP_STATE_KEY] = "legacy"
        await self._legacy(scope, receive, send)

    async def _serve_spa_file(self, scope: Scope, receive: Receive, send: Send) -> None:
        assert self._spa is not None
        immutable = scope["path"].startswith("/assets/")

        async def send_cached(message: Message) -> None:
            if immutable and message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = _IMMUTABLE
            await send(message)

        await self._spa(scope, receive, send_cached)

    def _index(self) -> Response:
        assert self._spa_index is not None
        return FileResponse(self._spa_index, headers={"Cache-Control": "no-cache"})

    @staticmethod
    def _exists(files: StaticFiles, relative: str) -> bool:
        if not relative or relative.endswith("/"):
            return False
        _, found = files.lookup_path(relative)
        return found is not None and not stat.S_ISDIR(found.st_mode)
