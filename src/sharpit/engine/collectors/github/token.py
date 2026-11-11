"""Stub: the GitHub token provider lands with the refresh action (W7 Task G2)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

Runner = Callable[..., Any]


@dataclass(frozen=True)
class Token:
    value: str
    source: str


def resolve_token(
    timeout: float | None, environ: Mapping[str, str] | None = None, run: Runner | None = None
) -> Token | None:
    return None
