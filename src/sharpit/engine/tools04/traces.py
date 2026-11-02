from __future__ import annotations

from typing import Any

from sharpit.engine.capture.traces import span_buffer
from sharpit.engine.tools import _LIMIT_ONLY, _NONE, Tool  # pyright: ignore[reportPrivateUsage]


def _clear(ctx: Any) -> dict[str, Any]:
    buffer = span_buffer(ctx)
    buffer.clear()
    return buffer.list(100)


TOOLS = (
    Tool(
        "get_traces",
        "Return a newest-first list of the OpenTelemetry traces this application recorded: root span, HTTP path, "
        "services, epoch-nanosecond timing, span count and error/AI flags. Span attributes are masked. Requires the "
        "application's own OpenTelemetry SDK TracerProvider; sharpit never installs one.",
        _LIMIT_ONLY,
        "traces",
        False,
        lambda c, a: span_buffer(c.ctx).list(a["limit"]),
    ),
    Tool(
        "clear_traces",
        "Clear the bounded in-memory span buffer and return the resulting empty report. This does not change the "
        "application's tracer provider or exporters.",
        _NONE,
        "traces",
        True,
        lambda c, _a: _clear(c.ctx),
    ),
)
COMMANDS = {"get_traces": "traces", "clear_traces": "traces clear"}
