"""A real ``uvicorn.Server`` with an open stream shuts down within the stream lifetime + 1 s (spec §10).

uvicorn sends ``lifespan.shutdown`` only after open responses drain, so the short stream lifetime is what bounds a
``--reload`` restart. The only test that keeps the 3 s default ``stream_max_seconds``.
"""

from __future__ import annotations

import asyncio
import http.client
import socket
import threading
import time

import uvicorn

from fastapi import FastAPI
from sharpit import install


def test_stream_shutdown_within_lifetime():
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    lifetime = handle.settings.stream_max_seconds
    assert lifetime == 3.0
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))  # port 0: no lease needed
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, lifespan="on"))
    thread = threading.Thread(target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", "/sharpit/api/log-tail/stream")
        resp = conn.getresponse()
        assert resp.status == 200
        assert resp.getheader("content-type", "").startswith("text/event-stream")
        started = time.monotonic()
        server.should_exit = True
        thread.join(lifetime + 5)
        elapsed = time.monotonic() - started
        assert not thread.is_alive()
        assert elapsed <= lifetime + 1, elapsed
        assert resp.read().endswith(b"retry: 1000\n\n")  # the stream ended itself, with the reconnect hint
        conn.close()
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
    wiring = handle.context.capture.wiring
    assert wiring is not None
    assert wiring.detached
