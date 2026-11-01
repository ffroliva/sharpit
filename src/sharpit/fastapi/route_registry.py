"""Route registration boundary used by the FastAPI adapter."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def register_routes(app: Any, routes: Iterable[Any]) -> None:
    """Add the adapter's ordered routes to a Starlette application."""
    return None
