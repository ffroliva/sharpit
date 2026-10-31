"""Request correlation (spec §9): the id ``CaptureMiddleware`` sets is the one every kind of handler code sees."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send

from fastapi import BackgroundTasks, Depends, FastAPI
from sharpit import install
from sharpit.engine.capture.correlation import INTERNAL, REQUEST, RequestInfo, internal, new_request_id
from sharpit.fastapi.adapter import SharpitHandle

LOCAL = ("127.0.0.1", 50000)


def _seen() -> str | None:
    info = REQUEST.get()
    return None if info is None else info.id


SEEN: dict[str, Any] = {}


def dependency() -> str | None:  # module level: FastAPI resolves string annotations against module globals
    SEEN["dependency"] = _seen()
    return SEEN["dependency"]


def _app(seen: dict[str, Any]) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()

    @app.get("/async")
    async def async_endpoint() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        seen["async"] = _seen()
        return {}

    @app.get("/sync")
    def sync_endpoint(dep: Annotated[str | None, Depends(dependency)]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        seen["sync"] = _seen()
        return {}

    @app.get("/background")
    async def background(tasks: BackgroundTasks) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        tasks.add_task(lambda: seen.__setitem__("background", _seen()))
        return {}

    @app.get("/child")
    async def child() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        async def work() -> None:
            seen["child"] = _seen()

        await asyncio.create_task(work())
        return {}

    return app, install(app, enabled="ON", show_banner=False)


def _get(path: str) -> tuple[dict[str, Any], str]:
    SEEN.clear()
    seen = SEEN
    app, handle = _app(seen)
    assert TestClient(app, client=LOCAL).get(path).status_code == 200
    buffer = handle.context.capture.exchanges
    assert buffer is not None
    return seen, buffer.report(None, None, None, None, None)["exchanges"][0]["id"]


def test_request_id_in_async_endpoint():
    seen, rid = _get("/async")
    assert seen["async"] == rid
    assert len(rid) == 16


def test_request_id_in_sync_endpoint_and_dependency():
    # anyio copies the context into the thread pool: tested, not assumed (spec §9)
    seen, rid = _get("/sync")
    assert seen["sync"] == seen["dependency"] == rid


def test_request_id_in_background_task():
    seen, rid = _get("/background")
    assert seen["background"] == rid


def test_request_id_in_create_task_child():
    seen, rid = _get("/child")
    assert seen["child"] == rid


class _Spy:
    """An inner host middleware: it sees sharpit's requests too (the mount is in the router, below it)."""

    def __init__(self, app: ASGIApp, seen: dict[str, str | None]) -> None:
        self.app = app
        self.seen = seen

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            self.seen[scope["path"]] = _seen()
        await self.app(scope, receive, send)


def test_no_id_for_sharpit_paths():
    seen: dict[str, str | None] = {}
    app = FastAPI()
    app.add_middleware(_Spy, seen=seen)
    app.get("/host")(lambda: {})
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, client=LOCAL, base_url="http://localhost")
    assert client.get("/sharpit/api/panels").status_code == 200
    assert client.get("/host").status_code == 200
    assert seen["/sharpit/api/panels"] is None
    assert seen["/host"] is not None


def test_root_path_self_exclusion():
    seen: dict[str, str | None] = {}
    app = FastAPI()
    app.add_middleware(_Spy, seen=seen)
    app.get("/host")(lambda: {})
    handle = install(app, enabled="ON", show_banner=False)
    client = TestClient(app, client=LOCAL, base_url="http://localhost", root_path="/api")
    # a server started with --root-path /api keeps the prefix in scope["path"] (ASGI 3)
    assert client.get("/api/sharpit/api/panels").status_code == 200
    assert client.get("/api/host").status_code == 200
    buffer = handle.context.capture.exchanges
    assert buffer is not None
    report = buffer.report(None, None, None, None, None)
    assert [e["path"] for e in report["exchanges"]] == ["/api/host"]
    assert report["hiddenSelf"] == 1
    assert seen["/api/sharpit/api/panels"] is None


def test_helpers():
    assert REQUEST.get() is None and INTERNAL.get() is False
    with internal():
        assert INTERNAL.get() is True
    assert INTERNAL.get() is False
    assert new_request_id() != new_request_id()
    assert RequestInfo("i", "c", "GET", "/", None, 0, None).finished_ns is None
