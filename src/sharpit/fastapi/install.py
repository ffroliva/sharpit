"""Capture setup performed while installing sharpit on a host application."""

from __future__ import annotations

from typing import Any

from sharpit.engine.context import SharpitContext
from sharpit.fastapi.capture import CaptureWiring
from sharpit.settings import SharpitSettings


def _configure_capture(app: Any, ctx: SharpitContext, settings: SharpitSettings) -> None:
    return None
