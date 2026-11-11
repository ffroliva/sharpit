"""The sole gatekeeper for an already imported Prometheus registry."""

from __future__ import annotations

from sys import modules
from typing import Any

REGISTRY: Any | None = None


def registry() -> Any | None:
    if REGISTRY is not None:
        return REGISTRY
    client = modules.get("prometheus_client")
    return getattr(client, "REGISTRY", None) if client is not None else None
