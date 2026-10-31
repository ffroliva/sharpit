"""Every ``ChangeStream`` SSE route (spec §10): a tick, the lifetime, a freed slot, the headers.

Each panel task adds its route to ``ROUTES``: (id, path, a function that makes the panel's data change).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import OpenStream
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.headers import NO_STORE
from sharpit.fastapi.adapter import SharpitHandle


def _raise_into_exceptions(handle: SharpitHandle) -> None:
    store = handle.context.capture.exceptions
    assert store is not None
    try:
        raise RuntimeError("tick")
    except RuntimeError as exc:
        store.record(exc, "log", None, "test")


ROUTES: list[tuple[str, str, Callable[[SharpitHandle], None]]] = [
    ("exceptions", "/sharpit/api/exceptions/stream", _raise_into_exceptions),
]

_HANDLES: list[SharpitHandle] = []


@pytest.fixture(autouse=True)
def _uninstall() -> Iterator[None]:
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()


def _handle(**options: Any) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()
    handle = install(app, **{"enabled": "ON", "show_banner": False, **options})
    _HANDLES.append(handle)
    return app, handle


def _slots(handle: SharpitHandle) -> int:
    slots = handle.context.capture.stream_slots
    assert slots is not None
    return slots.count


@pytest.mark.parametrize(("panel", "path", "change"), ROUTES, ids=[r[0] for r in ROUTES])
def test_signal_gives_one_update(panel: str, path: str, change: Callable[[SharpitHandle], None]):
    app, handle = _handle(stream_max_seconds=30)

    async def main() -> str:
        stream = OpenStream(app, path)
        await asyncio.wait_for(stream.started.wait(), 5)
        await asyncio.sleep(0.05)  # subscribed
        change(handle)
        for _ in range(50):  # within 1 s
            if "event: update" in stream.body:
                break
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.3)  # a coalesced tick: one burst, one event
        stream.task.cancel()
        await asyncio.gather(stream.task, return_exceptions=True)
        return stream.body

    body = asyncio.run(main())
    assert body.count("event: update") == 1, (panel, body)
    data = next(line for line in body.splitlines() if line.startswith("data: "))
    assert isinstance(json.loads(data[len("data: ") :])["ts"], int)


@pytest.mark.parametrize(("panel", "path", "change"), ROUTES, ids=[r[0] for r in ROUTES])
def test_stream_ends_after_lifetime_with_retry(panel: str, path: str, change: Callable[[SharpitHandle], None]):
    del change
    app, _ = _handle(stream_max_seconds=0.05)
    resp = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)).get(path)
    assert resp.status_code == 200 and resp.text.endswith("retry: 1000\n\n"), panel


@pytest.mark.parametrize(("panel", "path", "change"), ROUTES, ids=[r[0] for r in ROUTES])
def test_cancelled_client_frees_its_slot(panel: str, path: str, change: Callable[[SharpitHandle], None]):
    del change
    app, handle = _handle(stream_max_seconds=30)

    async def main() -> None:
        stream = OpenStream(app, path)
        await asyncio.wait_for(stream.started.wait(), 5)
        assert _slots(handle) == 1, panel
        stream.task.cancel()  # a client disconnect arrives as CancelledError
        await asyncio.gather(stream.task, return_exceptions=True)

    asyncio.run(main())
    assert _slots(handle) == 0


@pytest.mark.parametrize(("panel", "path", "change"), ROUTES, ids=[r[0] for r in ROUTES])
def test_stream_headers(panel: str, path: str, change: Callable[[SharpitHandle], None]):
    del change
    app, _ = _handle(stream_max_seconds=0.05)
    resp = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)).get(path)
    assert resp.headers["x-accel-buffering"] == "no", panel
    assert resp.headers["cache-control"] == NO_STORE
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["content-type"].startswith("text/event-stream")
