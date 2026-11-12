"""The request body limit (P2-M8-T03, plan §12): FastAPI reads a whole form or JSON body
before the route's login and CSRF dependencies run, so a body larger than its route takes is
refused with 413 before it is read: at once when it declares its length, as it streams when
it does not."""

import asyncio
import json

from starlette.types import Message, Receive, Scope, Send

from riso.api.limits import DOCUMENTS_LIMIT, IMPORT_LIMIT, JSON_LIMIT, MIB, body_limit
from riso.api.middleware import BodySizeLimitMiddleware


def test_uploads_take_their_files_and_everything_else_json():
    assert body_limit("POST", "/api/customers/c-1/documents") == DOCUMENTS_LIMIT
    assert DOCUMENTS_LIMIT == 20 * 20 * MIB + MIB
    assert body_limit("POST", "/api/customers/c-1/imports") == IMPORT_LIMIT
    assert body_limit("POST", "/api/admin/imports") == IMPORT_LIMIT
    assert IMPORT_LIMIT == 21 * MIB
    assert body_limit("POST", "/api/auth/login") == JSON_LIMIT
    assert body_limit("PUT", "/api/customers/c-1/documents") == JSON_LIMIT
    assert body_limit("POST", "/api/customers/c-1/documents/d-1") == JSON_LIMIT


# The middleware alone, around an app that reads the body ---------------------------------


def _scope(headers: list[tuple[bytes, bytes]]) -> Scope:
    return {"type": "http", "method": "POST", "path": "/x", "headers": headers}


def _run(chunks: list[bytes], *, declared: int | None, limit: int = 10):
    """Runs the middleware with `limit` around an app that reads the whole body and answers
    200 with its size, or 400 when reading failed (as FastAPI's body parsing does)."""
    reads: list[int] = []
    sent: list[Message] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        size = 0
        try:
            while True:
                message = await receive()
                size += len(message.get("body", b""))
                reads.append(size)
                if not message.get("more_body"):
                    break
            status = 200
        except Exception:
            status = 400
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": str(size).encode()})

    queue = [
        {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
        for i, chunk in enumerate(chunks)
    ]

    async def receive() -> Message:
        return queue.pop(0)

    async def send(message: Message) -> None:
        sent.append(message)

    headers = [] if declared is None else [(b"content-length", str(declared).encode())]
    middleware = BodySizeLimitMiddleware(app, limit_for=lambda method, path: limit)
    asyncio.run(middleware(_scope(headers), receive, send))
    return sent, reads


def _status(sent: list[Message]) -> int:
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) == 1, sent
    return int(starts[0]["status"])


def test_a_declared_length_over_the_limit_is_refused_before_anything_is_read():
    sent, reads = _run([b"x" * 11], declared=11)
    assert _status(sent) == 413
    assert reads == []
    body = json.loads(sent[-1]["body"])
    assert body["code"] == "too_large"


def test_a_body_without_a_length_is_cut_at_the_limit_and_the_apps_answer_replaced():
    sent, reads = _run([b"x" * 6, b"x" * 6, b"x" * 6], declared=None)
    assert _status(sent) == 413
    assert reads == [6]  # the second chunk passed the limit and was never handed over
    assert json.loads(sent[-1]["body"])["code"] == "too_large"


def test_a_body_that_lies_about_its_length_is_cut_too():
    sent, _ = _run([b"x" * 6, b"x" * 6], declared=4)
    assert _status(sent) == 413


def test_a_body_within_the_limit_passes():
    sent, reads = _run([b"x" * 5, b"x" * 5], declared=10)
    assert _status(sent) == 200
    assert reads == [5, 10]


# Through the app ---------------------------------------------------------------------------


def test_an_anonymous_oversized_json_body_is_refused_with_413_and_the_headers(client):
    response = client.post(
        "/api/auth/login",
        content=b'{"email": "' + b"a" * JSON_LIMIT + b'"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "too_large"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "X-Request-ID" in response.headers


def test_a_streamed_upload_over_the_limit_is_refused_before_the_login_check(client):
    def stream():
        chunk = b"x" * MIB
        for _ in range(IMPORT_LIMIT // MIB + 2):
            yield chunk

    response = client.post(
        "/api/customers/c-unknown/imports",
        content=stream(),
        headers={"Content-Type": "multipart/form-data; boundary=b"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "too_large"


def test_an_ordinary_request_is_untouched(client):
    response = client.post("/api/auth/login", json={"email": "nobody@x.test", "password": "x"})
    assert response.status_code == 401
