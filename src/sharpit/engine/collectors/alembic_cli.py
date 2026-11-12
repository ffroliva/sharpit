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
import threading
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

TIMEOUT = 600.0  # hard cap, no setting (plan DEFAULT TAKEN 3)
MAX_OUTPUT_BYTES = 1024 * 1024  # kept from the end; the caller masks, then caps the response at 4 KiB
_REAP = 5.0  # seconds to collect output after a kill


@dataclass(frozen=True)
class RunResult:
    returncode: int | None
    output: str
    failure: str | None  # None, "timeout" or "error"


class _Tail:
    """Reads a pipe on a thread, keeping only the last ``MAX_OUTPUT_BYTES``: a chatty child cannot grow memory."""

    def __init__(self, stream: Any) -> None:
        self._parts: deque[bytes] = deque()
        self._size = 0
        self._total = 0
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._pump, args=(stream,), daemon=True)
        self._thread.start()

    def _pump(self, stream: Any) -> None:
        with contextlib.suppress(OSError, ValueError):
            while chunk := stream.read1(65536):
                with self._lock:
                    self._parts.append(chunk)
                    self._size += len(chunk)
                    self._total += len(chunk)
                    while self._size - len(self._parts[0]) >= MAX_OUTPUT_BYTES:
                        self._size -= len(self._parts.popleft())

    def text(self, wait: float) -> str:
        """The kept tail once the pipe closed (or after ``wait`` seconds: a grandchild may still hold it)."""
        self._thread.join(wait)
        with self._lock:
            data = b"".join(self._parts)
            cut = self._total > MAX_OUTPUT_BYTES
        text = data[-MAX_OUTPUT_BYTES:].decode("utf-8", "replace")
        return text.partition("\n")[2] if cut else text  # drop the partial first line: a cut secret must not survive


def _kill_tree(proc: Any) -> None:
    pid = proc.pid
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


def _reap(proc: Any) -> None:
    with contextlib.suppress(subprocess.SubprocessError, OSError, ValueError):
        proc.wait(timeout=_REAP)  # collect the killed child so no zombie remains on POSIX


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
    tail = _Tail(proc.stdout)
    try:
        proc.wait(timeout=limit)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        _reap(proc)
        return RunResult(None, tail.text(_REAP), "timeout")
    except (OSError, ValueError) as exc:
        _kill_tree(proc)
        _reap(proc)
        return RunResult(None, f"{type(exc).__name__}: {exc}", "error")
    return RunResult(proc.returncode, tail.text(_REAP), None)
