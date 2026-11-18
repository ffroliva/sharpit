"""HTTP client for a running sharpit application."""

from __future__ import annotations

from typing import Any


class ClientError(Exception):
    """A safe-to-display CLI transport failure."""


class Client:
    def __init__(self, options: Any) -> None:
        self.options = options

    def get(self, path: str) -> Any:
        return None

    def invoke(self, tool: str, arguments: dict[str, Any]) -> Any:
        return None

    def catalog(self) -> Any:
        return None
