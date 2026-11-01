"""Route construction boundary for the FastAPI adapter."""

from __future__ import annotations

from typing import Any

from starlette.routing import BaseRoute

from sharpit.engine.context import SharpitContext


def build_routes(ctx: SharpitContext, host_app: Any) -> list[BaseRoute]:
    return []
