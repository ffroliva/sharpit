"""The GitHub token for the refresh action (port of BootUI ``DefaultGitHubTokenProvider``).

The only ``subprocess`` importer in ``src/`` (AGENTS.md rule 4): it runs ``gh auth token`` and nothing else, only from
the refresh action, never from a read. The token value never reaches a DTO, an exception message or a log record.

Beyond BootUI: ``gh`` is resolved to an absolute path from absolute ``PATH`` entries only, and never inside the working
directory (the app's own tree), so a ``gh`` planted in the project is not run (Windows searches the cwd first); its
output is read bounded, and a hung ``gh`` is killed at the timeout.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT = 5.0
MAX_OUTPUT_BYTES = 4096  # a token is ~40-100 bytes

Runner = Callable[..., Any]  # subprocess.Popen, injectable for tests


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
    gh = find_gh(env.get("PATH", ""))
    if gh is None:
        return None
    return _gh_token(gh, safe_timeout(timeout), run or subprocess.Popen)


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def find_gh(search_path: str) -> str | None:
    """The first ``gh`` on the absolute ``PATH`` entries that is not inside the working directory."""
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        return None
    for entry in search_path.split(os.pathsep):
        if not entry or not os.path.isabs(entry):
            continue  # an empty or relative entry means the working directory
        # a directory part makes shutil.which look only there (no implicit cwd on Windows), PATHEXT still applies
        found = shutil.which(os.path.join(entry, "gh"))
        try:
            if found is not None and not _inside(Path(found).resolve(), cwd):
                return found
        except OSError:
            continue
    return None


def _gh_token(gh: str, timeout: float, run: Runner) -> Token | None:
    try:
        proc = run(
            [gh, "auth", "token"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    killer = threading.Timer(timeout, proc.kill)  # a hung gh is killed, which also ends the read below
    killer.daemon = True
    killer.start()
    try:
        output = bytes(proc.stdout.read(MAX_OUTPUT_BYTES + 1))
        if len(output) > MAX_OUTPUT_BYTES:
            return None
        if proc.wait(timeout) != 0:
            return None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    finally:
        killer.cancel()
        if proc.poll() is None:
            proc.kill()
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                proc.wait(timeout)  # reap it
        proc.stdout.close()
    value = output.decode("utf-8", "replace").strip()
    return Token(value, "gh auth token") if value else None
