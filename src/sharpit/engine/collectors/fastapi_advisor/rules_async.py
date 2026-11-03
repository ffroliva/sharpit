"""Async and I/O rules over route handlers and app source: blocking calls, outbound HTTP timeouts, background work."""

from __future__ import annotations

from sharpit.engine.advisors.rules import RuleDefinition

_CONCURRENCY = "https://fastapi.tiangolo.com/async/"
_BACKGROUND = "https://fastapi.tiangolo.com/tutorial/background-tasks/"
_TIMEOUTS = "https://requests.readthedocs.io/en/latest/user/advanced/#timeouts"

SYNC_IO = RuleDefinition(
    "FASTAPI-ASYNC-001",
    "Review blocking work in sync endpoints",
    "Performance and concurrency",
    "INFO",
    "A sync def endpoint that blocks on I/O holds one of the threadpool's worker threads (40 by default) for the "
    "whole call.",
    "Keep it sync if the work is short, or make the endpoint async def with an async client for long waits.",
    _CONCURRENCY,
)
ASYNC_BLOCKING = RuleDefinition(
    "FASTAPI-ASYNC-002",
    "Blocking call inside an async endpoint",
    "Performance and concurrency",
    "HIGH",
    "A blocking call (time.sleep, requests, subprocess, file or socket I/O) inside an async def endpoint stops the "
    "event loop: every other request waits until it returns.",
    "Use the async equivalent (asyncio.sleep, httpx.AsyncClient), run the call with run_in_threadpool, or make the "
    "endpoint a plain def.",
    _CONCURRENCY,
)
HTTP_TIMEOUT = RuleDefinition(
    "FASTAPI-HTTP-001",
    "Outbound HTTP call without a timeout",
    "Web and HTTP",
    "LOW",
    "requests has no default timeout: a call to a server that stops answering hangs its worker indefinitely.",
    "Pass timeout= to every requests call, or use httpx, which defaults to 5 seconds.",
    _TIMEOUTS,
)
HEAVY_BACKGROUND = RuleDefinition(
    "FASTAPI-BG-001",
    "Review heavy work in BackgroundTasks",
    "Performance and concurrency",
    "LOW",
    "BackgroundTasks run in the same process after the response, with no retry or persistence; a task that loops "
    "or blocks competes with requests and is lost on restart.",
    "Keep background tasks short; move long or critical work to a task queue.",
    _BACKGROUND,
)
RULES = (SYNC_IO, ASYNC_BLOCKING, HTTP_TIMEOUT, HEAVY_BACKGROUND)
