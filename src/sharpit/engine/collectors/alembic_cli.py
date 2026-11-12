"""The Alembic child-process runner (W8 M1): the only place that starts ``python -m alembic`` (AGENTS.md rule 4).

Runs only from the migrate action, never from a read. The caller builds a fixed argv (``sys.executable -m alembic ...``,
never request text); this module adds ``shell=False``, a closed stdin, one merged output pipe, a hard time cap and a
tree kill on timeout. It returns raw output: masking and capping belong to the caller (``alembic.migrate``).

Beyond the GitHub token module's job object (``github/token.py``, a different collector, so not importable here by
rule 3): POSIX starts the child in its own process group and kills the group; Windows kills the tree with the system
``taskkill /T /F`` while the child is still alive, which is the timeout case. A grandchild orphaned earlier is not
reached on Windows (shortcut: upgrade to a job object if Alembic's env.py is ever seen spawning detached workers).
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

TIMEOUT = 600.0  # hard cap, no setting (plan DEFAULT TAKEN 3)
MAX_OUTPUT_BYTES = 1024 * 1024  # kept from the end; the caller masks, then caps the response at 4 KiB
_REAP = 5.0  # seconds to collect output after a kill
_POPEN = subprocess.Popen  # the real class, bound at import: a patched subprocess.Popen must not break isinstance


@dataclass(frozen=True)
class RunResult:
    returncode: int | None
    output: str
    failure: str | None  # None, "timeout" or "error"


def _text(raw: bytes | None) -> str:
    data = (raw or b"")[-MAX_OUTPUT_BYTES:]
    text = data.decode("utf-8", "replace")
    if len(raw or b"") > MAX_OUTPUT_BYTES:
        text = text.partition("\n")[2]  # drop the partial first line: a cut secret must not survive
    return text


def _kill_tree(proc: Any) -> None:
    pid = int(proc.pid) if isinstance(proc, _POPEN) else None
    if pid is not None:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            if sys.platform != "win32":
                os.killpg(pid, signal.SIGKILL)  # the child leads its own session
            else:
                taskkill = os.path.join(os.environ.get("SYSTEMROOT", "C:\\Windows"), "System32", "taskkill.exe")
                subprocess.run(  # noqa: S603  # absolute system taskkill, fixed arguments
                    [taskkill, "/T", "/F", "/PID", str(pid)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=_REAP,
                    check=False,
                )
    with contextlib.suppress(OSError):
        proc.kill()


def _drain(proc: Any) -> bytes | None:
    try:
        return proc.communicate(timeout=_REAP)[0]
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None  # a grandchild still holds the pipe: give up on the output, never hang


def run_alembic(
    argv: Sequence[str], cwd: str, timeout: float | None = None, popen: Callable[..., Any] | None = None
) -> RunResult:
    """Run ``argv`` in ``cwd`` and return its merged output; never raises, never outlives ``timeout``."""
    limit = timeout if timeout is not None and timeout > 0 else TIMEOUT
    session: dict[str, Any] = (
        {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
        if sys.platform == "win32"
        else {"start_new_session": True}
    )
    try:
        proc: Any = (popen or subprocess.Popen)(
            list(argv),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            **session,
        )
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return RunResult(None, f"{type(exc).__name__}: {exc}", "error")
    try:
        raw = proc.communicate(timeout=limit)[0]
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        return RunResult(None, _text(_drain(proc)), "timeout")
    except (OSError, ValueError) as exc:
        _kill_tree(proc)
        return RunResult(None, f"{type(exc).__name__}: {exc}", "error")
    return RunResult(proc.returncode, _text(raw), None)
