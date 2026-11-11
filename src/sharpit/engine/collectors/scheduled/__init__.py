"""Scheduled tasks from in-process schedulers (stub: lane C red commit)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any


@dataclass
class Discovery:
    present: bool
    tasks: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    limitations: list[str] = field(default_factory=list[str])


def build_report(_discovery: Discovery | None) -> dict[str, Any]:
    return {"schedulingPresent": None, "total": -1, "tasks": []}


def discover(_modules: Iterable[ModuleType]) -> Discovery:
    return Discovery(False)
