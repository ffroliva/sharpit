"""The ``security`` advisor's MCP read tools and CLI-only scan (WAVE-B §1, §2)."""

from __future__ import annotations

from typing import Any

from sharpit.engine.collectors.security.report import SecurityService
from sharpit.engine.context import SharpitContext

TOOLS: tuple[Any, ...] = ()
COMMANDS: dict[str, str] = {}


def security_service(ctx: SharpitContext) -> SecurityService:
    raise LookupError("security advisor is not wired")
