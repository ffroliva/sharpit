from __future__ import annotations

from typing import Any

from starlette.routing import BaseRoute


def build_routes(ctx: Any, host_app: Any = None) -> list[BaseRoute]:
    return []
