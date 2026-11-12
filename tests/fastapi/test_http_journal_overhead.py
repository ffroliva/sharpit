"""W5a P-http overhead: the ``http`` journal event is one flat dict offered after the response. Rounds of 1 000 requests
with the journal on (default sources) against the same install with ``runtime_journal_enabled=False``; every other
capture panel is on in both. Budget: a quarter of the capture middleware's 0.2 ms (`test_capture_overhead.py`), since
the event is twelve scalars and an O(1) ring append. How to read a failure: docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import asyncio

from starlette.responses import PlainTextResponse
from tests.fastapi.test_capture_overhead import REQUESTS, ROUNDS, SCOPE, _receive, _round_ns, _send
from tests.overhead import check_budget, paired

from fastapi import FastAPI
from sharpit import install
from sharpit.fastapi.adapter import SharpitHandle

BUDGET_MS = 0.05


def _app(journal: bool) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()

    @app.get("/bare")
    async def bare() -> PlainTextResponse:  # pyright: ignore[reportUnusedFunction]
        return PlainTextResponse("ok")

    return app, install(app, enabled="ON", show_banner=False, runtime_journal_enabled=journal)


def test_http_journal_request_overhead_budget():
    (off_app, _), (on_app, on_handle) = _app(False), _app(True)
    loop = asyncio.new_event_loop()
    try:
        for app in (off_app, on_app):
            loop.run_until_complete(app(dict(SCOPE), _receive, _send))  # builds the middleware stack outside the timing
        result = paired(
            lambda: loop.run_until_complete(_round_ns(off_app)),
            lambda: loop.run_until_complete(_round_ns(on_app)),
            ROUNDS,
        )
    finally:
        loop.close()
    journal = on_handle.context.capture.journal
    assert journal is not None
    assert journal.status()["recorded"].get("http", 0) >= REQUESTS, "the http event never ran: the number means nothing"
    check_budget("http journal event per request", result, BUDGET_MS * 1e6, "ms", 1e6)
