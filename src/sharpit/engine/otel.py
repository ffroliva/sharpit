"""OpenTelemetry gatekeeper (red stub)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class SharpitSpanProcessor:
    def on_start(self, span: Any, parent_context: Any = None) -> None:
        pass

    def _on_ending(self, span: Any) -> None:
        pass

    def on_end(self, span: Any) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


PROCESSOR = SharpitSpanProcessor()


def unavailable_reason() -> str | None:
    return None


def attach(sink: Any) -> Callable[[], None] | None:
    return None
