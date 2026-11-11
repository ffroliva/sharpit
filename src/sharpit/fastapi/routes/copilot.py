from __future__ import annotations

from typing import Any

from starlette.routing import BaseRoute

from sharpit.engine.collectors.agentsessions import Layout
from sharpit.fastapi.routes.agent_sessions import build_agent_sessions_routes


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    return build_agent_sessions_routes(ctx, Layout.COPILOT)
