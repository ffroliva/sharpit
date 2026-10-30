"""A fake ``urllib`` opener for the OSV and EPSS clients: records every request, never opens a socket."""

import io
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from email.message import Message
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parents[2] / "fixtures"

Reply = tuple[int, str | bytes] | BaseException
Handler = Callable[[urllib.request.Request], Reply]


def fixture_text(relative: str) -> str:
    return (FIXTURES / relative).read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = io.BytesIO(body)

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class FakeOpener:
    """Replies via ``handler(request)``: a ``(status, body)`` pair or an exception to raise. 4xx/5xx raise
    ``HTTPError`` as urllib's default opener does."""

    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float | None] = []

    def open(self, request: urllib.request.Request, data: Any = None, timeout: float | None = None) -> FakeResponse:
        self.requests.append(request)
        self.timeouts.append(timeout)
        reply = self.handler(request)
        if isinstance(reply, BaseException):
            raise reply
        status, body = reply
        raw = body.encode("utf-8") if isinstance(body, str) else body
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "error", Message(), io.BytesIO(raw))
        return FakeResponse(status, raw)

    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.data) for r in self.requests]  # type: ignore[arg-type]


def replies(*items: Reply) -> FakeOpener:
    """An opener answering successive requests with ``items`` in order."""
    queue = list(items)
    return FakeOpener(lambda _request: queue.pop(0))
