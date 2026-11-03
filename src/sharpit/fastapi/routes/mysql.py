"""``GET {api}/mysql`` and ``POST {api}/mysql/read`` (BootUI contract §6)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.routing import BaseRoute

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext


def build_routes(_ctx: SharpitContext, _host_app: object = None) -> list[BaseRoute]:
    return []
