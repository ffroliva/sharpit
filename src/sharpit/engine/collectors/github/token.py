"""The GitHub token for the refresh action (port of BootUI ``DefaultGitHubTokenProvider``).

The only ``subprocess`` importer in ``src/`` (AGENTS.md rule 4): it runs ``gh auth token`` and nothing else, only from
the refresh action, never from a read. The token value never reaches a DTO, an exception message or a log record.

Beyond BootUI: ``gh`` is resolved to an absolute path from absolute ``PATH`` entries only, and never inside the working
directory (the app's own tree), so a ``gh`` planted in the project is not run (Windows searches the cwd first); its
output is read bounded in a daemon thread abandoned at the timeout, and ``gh`` and its children are killed.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT = 5.0
MAX_OUTPUT_BYTES = 4096  # a token is ~40-100 bytes
_KILL_RESERVE = 0.5  # seconds of the lookup kept for the kill and reap
_POPEN = subprocess.Popen  # the real class, bound at import: a patched subprocess.Popen must not break isinstance

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


def _is_or_under(found: str, cwd: os.stat_result) -> bool:
    """Whether ``found`` or any of its ancestors is the working directory, by file identity, so every spelling of it
    (``\\\\?\\``, ``\\\\?\\GLOBALROOT\\??\\``, an admin share, a symlink) is caught."""
    path = Path(found).resolve()
    for candidate in (path, *path.parents):
        try:
            if os.path.samestat(os.stat(candidate), cwd):
                return True
        except OSError:
            continue
    return False


def find_gh(search_path: str) -> str | None:
    """The first ``gh`` on the absolute ``PATH`` entries that is not inside the working directory."""
    try:
        cwd = os.stat(os.getcwd())
    except OSError:
        return None
    for entry in search_path.split(os.pathsep):
        if not entry or not os.path.isabs(entry):
            continue  # an empty or relative entry means the working directory
        # a directory part makes shutil.which look only there (no implicit cwd on Windows), PATHEXT still applies
        found = shutil.which(os.path.join(entry, "gh"))
        try:
            if found is not None and not _is_or_under(found, cwd):
                return found
        except OSError:
            continue
    return None


class _Tree:
    """``gh`` and every process it starts. Windows: a job object, so the tree can be terminated after ``gh`` itself
    exited (a ``gh.cmd`` shim's child can hold stdout past the shim); POSIX: ``gh`` leads its own process group.
    A fake process (tests) is only ``kill()``ed."""

    def __init__(self, proc: Any) -> None:
        self.proc = proc
        self.pid: int | None = int(proc.pid) if isinstance(proc, _POPEN) else None
        self.job: int | None = None
        if sys.platform == "win32" and self.pid is not None:
            # shortcut: a process gh starts before this assignment escapes the job; Popen returns before gh (or a
            # cmd.exe shim) has loaded, so none in practice; a failed assignment falls back to taskkill /T
            self.job = _job_for(self.pid)

    def kill(self, timeout: float) -> None:
        if self.pid is not None:
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                if sys.platform != "win32":
                    os.killpg(self.pid, signal.SIGKILL)  # gh was started in its own session
                elif self.job is not None:
                    _KERNEL32.TerminateJobObject(self.job, 1)
                else:
                    _taskkill(self.pid, timeout)
        with contextlib.suppress(OSError):
            self.proc.kill()

    def close(self) -> None:
        if sys.platform == "win32" and self.job is not None:
            _KERNEL32.CloseHandle(self.job)
            self.job = None


if sys.platform == "win32":
    import ctypes

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _KERNEL32.CreateJobObjectW.restype = ctypes.c_void_p
    _KERNEL32.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
    _KERNEL32.OpenProcess.restype = ctypes.c_void_p
    _KERNEL32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    _KERNEL32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    _KERNEL32.TerminateJobObject.argtypes = (ctypes.c_void_p, ctypes.c_uint)
    _KERNEL32.CloseHandle.argtypes = (ctypes.c_void_p,)
    _SET_QUOTA_AND_TERMINATE = 0x0100 | 0x0001

    def _job_for(pid: int) -> int | None:
        job = _KERNEL32.CreateJobObjectW(None, None)
        if not job:
            return None
        process = _KERNEL32.OpenProcess(_SET_QUOTA_AND_TERMINATE, 0, pid)
        assigned = bool(process) and bool(_KERNEL32.AssignProcessToJobObject(job, process))
        if process:
            _KERNEL32.CloseHandle(process)
        if not assigned:
            _KERNEL32.CloseHandle(job)
            return None
        return int(job)

    def _taskkill(pid: int, timeout: float) -> None:
        system = os.environ.get("SYSTEMROOT", "C:\\Windows")
        taskkill = os.path.join(system, "System32", "taskkill.exe")  # absolute: never a planted taskkill
        subprocess.run(  # noqa: S603 (absolute system taskkill, fixed arguments)
            [taskkill, "/T", "/F", "/PID", str(pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=max(0.1, timeout),
            check=False,
        )


def _read_output(proc: Any, box: list[bytes]) -> None:
    with contextlib.suppress(OSError, ValueError):
        box.append(bytes(proc.stdout.read(MAX_OUTPUT_BYTES + 1)))


def _gh_token(gh: str, timeout: float, run: Runner) -> Token | None:
    """One bound for everything: the read, the exit wait, the tree kill and the reap all share ``timeout``."""
    end = time.monotonic() + timeout

    def left() -> float:
        return max(0.0, end - time.monotonic())

    session = {} if sys.platform == "win32" else {"start_new_session": True}
    try:
        proc = run(
            [gh, "auth", "token"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            **session,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    tree = _Tree(proc)
    box: list[bytes] = []
    # the read runs in a daemon thread: a pipe a grandchild keeps open cannot hold the refresh past the timeout
    reader = threading.Thread(target=_read_output, args=(proc, box), name="sharpit-gh-token", daemon=True)
    reader.start()
    reader.join(max(0.0, left() - min(_KILL_RESERVE, timeout / 5)))  # keep time to kill and reap
    try:
        if reader.is_alive() or not box or len(box[0]) > MAX_OUTPUT_BYTES:
            return None
        if proc.wait(left()) != 0:
            return None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    finally:
        _release(proc, tree, reader, left)
    value = box[0].decode("utf-8", "replace").strip()
    return Token(value, "gh auth token") if value else None


def _release(proc: Any, tree: _Tree, reader: threading.Thread, left: Callable[[], float]) -> None:
    """Kill the tree when gh still runs or anything still holds its stdout, then reap, end the reader, close."""
    if reader.is_alive() or proc.poll() is None:
        tree.kill(left())
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            proc.wait(left())
        reader.join(left())
    if not reader.is_alive():
        with contextlib.suppress(OSError):
            proc.stdout.close()
    tree.close()
