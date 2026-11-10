"""MCP replies are byte-identical to the base before the handler-table dispatch (review R5).

``tests/fixtures/mcp_dispatch_golden.json`` was generated once by running this file as a script against the base
commit's ``src`` (``origin/release/0.6.0``, a scratch worktree removed afterwards)::

    PYTHONPATH=<base worktree>/src python tests/engine/test_mcp_dispatch_golden.py <fixture path>

Nothing is normalised: every case uses a fixed id, a fake tool with a constant payload and no clock, so each reply is
the same bytes on every run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.context import SharpitContext
from sharpit.engine.mcp import PROMPTS, PROTOCOL_VERSION, McpServer
from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo
from sharpit.engine.tools import Tool, ToolCallError
from sharpit.settings import load_settings

FIXTURE = Path(__file__).parents[1] / "fixtures" / "mcp_dispatch_golden.json"
JSON = {"content-type": "application/json"}
SCOPE = {"server": ("127.0.0.1", 8000)}
NONE_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


class _Introspector:
    def app_info(self) -> AppInfo:
        return AppInfo("demo", "FastAPI", "0.115.0", None)

    def routes(self) -> list[RouteInfo]:
        return []

    def providers(self) -> list[ProviderInfo]:
        return []


def _refuse(_call: object, _arguments: dict[str, Any]) -> dict[str, Any]:
    raise ToolCallError("refused by the fake tool", 400)


TOOLS = (
    Tool("get_fake", "Read a constant.", NONE_SCHEMA, "overview", False, lambda _c, _a: {"ok": True, "n": 1}),
    Tool("get_refusal", "Always refuses.", NONE_SCHEMA, "overview", False, _refuse),
    Tool("do_fake", "An action, never listed.", NONE_SCHEMA, "overview", True, lambda _c, _a: {}),
)


def _rpc(method: str, rid: object = 1, params: object = None) -> dict[str, object]:
    body: dict[str, object] = {"jsonrpc": "2.0", "method": method}
    if rid is not None:
        body["id"] = rid
    if params is not None:
        body["params"] = params
    return body


CASES: dict[str, tuple[bool, dict[str, object]]] = {
    "initialize default version": (True, _rpc("initialize", 1, {})),
    "initialize echoed version": (True, _rpc("initialize", 2, {"protocolVersion": PROTOCOL_VERSION})),
    "ping": (True, _rpc("ping", 3)),
    "tools/list": (True, _rpc("tools/list", 4)),
    "tools/call ok": (True, _rpc("tools/call", 5, {"name": "get_fake", "arguments": {}})),
    "tools/call refused": (True, _rpc("tools/call", 6, {"name": "get_refusal", "arguments": {}})),
    "tools/call unknown tool": (True, _rpc("tools/call", 7, {"name": "does_not_exist"})),
    "tools/call bad arguments": (True, _rpc("tools/call", 8, {"name": "get_fake", "arguments": "invalid"})),
    "prompts/list": (True, _rpc("prompts/list", 9)),
    "prompts/get known": (True, _rpc("prompts/get", 10, {"name": PROMPTS[0].name})),
    "prompts/get unknown": (True, _rpc("prompts/get", 11, {"name": "no-such-prompt"})),
    "notifications/cancelled as notification": (True, _rpc("notifications/cancelled", None, {"requestId": 1})),
    "notifications/cancelled with an id": (True, _rpc("notifications/cancelled", 12, {"requestId": 1})),
    "notifications/initialized": (True, _rpc("notifications/initialized", None)),
    "unknown method": (True, _rpc("no/such/method", 13)),
    "unknown method as notification": (True, _rpc("no/such/method", None)),
    "disabled request": (False, _rpc("tools/list", 14)),
    "disabled notification": (False, _rpc("notifications/initialized", None)),
}


def replies() -> dict[str, str]:
    """Each case's ``(status, body, headers)`` as JSON text, from one fresh server per case."""
    out: dict[str, str] = {}
    for name, (enabled, request) in CASES.items():
        ctx = SharpitContext(
            load_settings({"config_scan": False}, {}),
            ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ()),
            _Introspector(),
        )
        server = McpServer(ctx, tools=TOOLS)
        server.enabled = enabled
        status, body, headers = server.handle(json.dumps(request).encode(), JSON, SCOPE)
        out[name] = json.dumps([status, body, headers], ensure_ascii=False)
    return out


def test_mcp_dispatch_replies_are_byte_identical() -> None:
    golden: dict[str, str] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    current = replies()
    assert sorted(current) == sorted(golden)
    for name, reply in current.items():
        assert reply.encode("utf-8") == golden[name].encode("utf-8"), f"MCP reply changed: {name}"


if __name__ == "__main__":  # the one-time generation against the base commit (module docstring)
    Path(sys.argv[1]).write_text(
        json.dumps(replies(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
