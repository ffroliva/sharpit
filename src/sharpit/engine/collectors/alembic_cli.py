"""The Alembic child-process runner (W8 M1): skeleton, behaviour follows in the feature commit."""

from __future__ import annotations

import subprocess  # noqa: F401  # the gatekeeper for the Alembic actions (AGENTS.md rule 4)
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

TIMEOUT = 600.0


@dataclass(frozen=True)
class RunResult:
    returncode: int | None
    output: str
    failure: str | None  # None, "timeout" or "error"


def run_alembic(
    argv: Sequence[str], cwd: str, timeout: float | None = None, popen: Callable[..., Any] | None = None
) -> RunResult:
    return RunResult(None, "", "error")
