"""Whether the running code is the current request's own endpoint or dependency (security-sinks plan, D1)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def owned(scope: Mapping[str, Any]) -> bool:
    return False
