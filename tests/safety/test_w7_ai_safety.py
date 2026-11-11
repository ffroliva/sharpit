"""AI Framework reads have no side effects, and the panel gates every route and tool."""

PANEL = "ai"
GET_ROWS = [
    "/sharpit/api/ai/overview",
    "/sharpit/api/ai/chats",
    "/sharpit/api/ai/chats/{spanId}",
    "/sharpit/api/ai/tokens",
]
WRITE_ROWS: list[tuple[str, str]] = []
PATH_PARAMS = {"spanId": "0" * 16}
TOOL_ARGS = {}
TOOL_SEEDS = {}
