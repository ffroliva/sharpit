"""Span buffer (red stub)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sharpit.engine.masking import Masker


class SpanBuffer:
    def __init__(self, masker: Masker, *, capacity: int = 1000, self_path: str = "/sharpit") -> None:
        self.masker = masker

    def add(self, span: Any) -> None:
        pass

    def arm(self) -> Callable[[], None] | None:
        return None

    def list(self, limit: int) -> dict[str, Any]:
        return {"enabled": True, "unavailableReason": None, "retained": 0, "capacity": 0, "traces": []}

    def detail(self, trace_id: str) -> dict[str, Any] | None:
        return None

    def clear(self) -> None:
        pass
