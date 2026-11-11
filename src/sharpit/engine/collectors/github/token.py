"""The GitHub token for the refresh action (port of BootUI ``DefaultGitHubTokenProvider``).

The only ``subprocess`` importer in ``src/`` (AGENTS.md rule 4): it runs ``gh auth token`` and nothing else, only from
the refresh action, never from a read. The token value never reaches a DTO, an exception message or a log record.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

DEFAULT_TIMEOUT = 5.0
_GH = ("gh", "auth", "token")

Runner = Callable[..., Any]


@dataclass(frozen=True)
class Token:
    value: str = field(repr=False)  # repr=False: a logged or raised Token never shows the secret
    source: str


def safe_timeout(timeout: float | None) -> float:
    """BootUI ``safeTimeout``: a missing or non-positive timeout falls back to 5 s, never waits forever."""
    return timeout if timeout is not None and timeout > 0 else DEFAULT_TIMEOUT


def resolve_token(
    timeout: float | None, environ: Mapping[str, str] | None = None, run: Runner | None = None
) -> Token | None:
    """``GITHUB_TOKEN``, then ``GH_TOKEN``, then ``gh auth token``; trimmed, blanks skipped, ``None`` when none."""
    env = os.environ if environ is None else environ
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = env.get(name)
        if value is not None and value.strip():
            return Token(value.strip(), name)
    return _gh_token(safe_timeout(timeout), run or subprocess.run)


def _gh_token(timeout: float, run: Runner) -> Token | None:
    try:
        # gh from the developer's PATH on purpose (BootUI does the same); run() kills it on timeout
        done = run(
            list(_GH),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if done.returncode != 0:
        return None
    output = done.stdout
    value = (output.decode("utf-8", "replace") if isinstance(output, bytes) else str(output or "")).strip()
    return Token(value, "gh auth token") if value else None
