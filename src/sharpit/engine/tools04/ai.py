from __future__ import annotations

from sharpit.engine.capture.traces import span_buffer
from sharpit.engine.collectors.ai import ai_overview, ai_settings
from sharpit.engine.tools import _NONE, Tool  # pyright: ignore[reportPrivateUsage]

TOOLS = (
    Tool(
        "get_ai_overview",
        "Return token usage and counts from the GenAI spans recorded in the application's OpenTelemetry trace ring. "
        "Prompt and completion content is hidden unless SHARPIT_EXPOSE_VALUES=FULL.",
        _NONE,
        "ai",
        False,
        lambda c, _a: ai_overview(span_buffer(c.ctx), ai_settings(c.ctx.settings)),
    ),
)
COMMANDS = {"get_ai_overview": "ai overview"}
