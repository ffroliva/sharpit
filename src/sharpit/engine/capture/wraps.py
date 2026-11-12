"""A shared class-method wrap helper for capture integrations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def wrap(
    owner: type, name: str, make: Callable[[Callable[..., Any]], Callable[..., Any]], *, tag: str
) -> Callable[[], bool] | None:
    return lambda: False
