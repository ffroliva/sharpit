from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from starlette.requests import Request
from starlette.responses import Response

from sharpit.engine.collectors.agentsessions import Layout, session_store
from sharpit.fastapi.sse import sse_response

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext


def _dashboard_signature(dash: dict[str, Any]) -> str:
    return json.dumps(dash, sort_keys=True)


async def _agent_sessions_events(
    store: Any,
    debounce_seconds: float,
) -> AsyncIterator[tuple[str, str | None, str]]:
    sessions_dto = await asyncio.to_thread(store.sessions)
    yield "sessions", None, json.dumps(sessions_dto)
    dash = await asyncio.to_thread(store.dashboard)
    yield "dashboard", None, json.dumps(dash)
    prev_sig = _dashboard_signature(dash)

    debounce = max(0.05, debounce_seconds)
    while True:
        await asyncio.sleep(debounce)
        await asyncio.to_thread(store.refresh)
        curr_dash = await asyncio.to_thread(store.dashboard)
        curr_sig = _dashboard_signature(curr_dash)
        if curr_sig != prev_sig:
            prev_sig = curr_sig
            sessions_dto = await asyncio.to_thread(store.sessions)
            yield "sessions", None, json.dumps(sessions_dto)
            yield "dashboard", None, json.dumps(curr_dash)


def make_agent_sessions_stream_handler(ctx: SharpitContext, layout: Layout):
    store = session_store(ctx, layout)
    debounce_seconds = (
        ctx.settings.copilot_stream_debounce if layout == Layout.COPILOT else ctx.settings.claude_code_stream_debounce
    )

    def stream(_request: Request) -> Response:
        return sse_response(ctx, _agent_sessions_events(store, debounce_seconds))

    return stream
