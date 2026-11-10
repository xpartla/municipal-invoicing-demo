"""Serving the built SPA (the demo's Alpine pages were removed in P2-M4-T10).

This app is the router's default, so it runs only when no API route matched; API paths that
matched nothing get a JSON 404.

- `/` and every path without a file extension (a client route such as `/c/123/invoices`) get
  the SPA's `index.html`; the SPA's own files (`/assets/…`) are served from `spa_dir`, hashed
  assets with a year's caching.
- Without a built SPA (no `index.html` in `spa_dir`), a page says how to build it.
"""

import stat
from pathlib import Path, PurePosixPath

from starlette.datastructures import MutableHeaders
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Message, Receive, Scope, Send

_IMMUTABLE = "public, max-age=31536000, immutable"


NOT_BUILT = "The frontend is not built: run `pnpm build` in frontend/ (see README.md)."


class FrontendFiles:
    def __init__(self, spa_dir: Path | None = None) -> None:
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
            await PlainTextResponse(NOT_BUILT, status_code=503)(scope, receive, send)
            return
        if path == "/":
            await self._index()(scope, receive, send)
            return
        if self._exists(self._spa, path.lstrip("/")):
            await self._serve_spa_file(scope, receive, send)
        elif "." not in PurePosixPath(path).name:
            await self._index()(scope, receive, send)
        else:
            await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)

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
