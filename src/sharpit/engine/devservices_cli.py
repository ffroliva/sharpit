"""The docker CLI gatekeeper: the only module that spawns a process for dev-services restart (W8 D1).

Fixed argv list, ``shell=False``, an absolute ``docker`` that is never found through the working directory, stdin
closed, a hard timeout that kills the process, and output read through a bounded buffer.
"""

from __future__ import annotations

import contextlib
import os
import re
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass

DOCKER_TIMEOUT_S = 60.0
MAX_OUTPUT_BYTES = 16384
_DRAIN_CHUNK = 65536
_CONTAINER_ID = re.compile(r"[0-9a-f]{12,64}")
_EXE = "docker.exe" if os.name == "nt" else "docker"  # never docker.cmd or .bat: those would start a shell


@dataclass(frozen=True)
class CliResult:
    """``returncode`` is None when the process never ran to an exit (spawn error, refused id, timeout)."""

    returncode: int | None
    timed_out: bool
    output: str


def is_container_id(value: str) -> bool:
    return _CONTAINER_ID.fullmatch(value) is not None


def resolve_docker(path_env: str | None = None) -> str | None:
    """The first executable ``docker`` in an absolute PATH entry; the working directory is never searched."""
    raw = os.environ.get("PATH", "") if path_env is None else path_env
    for entry in raw.split(os.pathsep):
        entry = entry.strip().strip('"')
        if not entry or not os.path.isabs(entry):
            continue
        candidate = os.path.join(entry, _EXE)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _kill(proc: subprocess.Popen[bytes]) -> None:
    with contextlib.suppress(OSError):
        if sys.platform == "win32":
            proc.kill()  # shortcut: the process only, not its tree; docker restart spawns none
        else:
            os.killpg(proc.pid, signal.SIGKILL)  # the child leads its own session, so this takes the group


def _drain(proc: subprocess.Popen[bytes], kept: list[bytes]) -> None:
    stream = proc.stdout
    if stream is None:
        return
    kept.append(stream.read(MAX_OUTPUT_BYTES))
    while stream.read(_DRAIN_CHUNK):  # keep reading so the child never blocks on a full pipe; the rest is dropped
        pass


def run_argv(argv: list[str], timeout: float = DOCKER_TIMEOUT_S) -> CliResult:
    try:
        proc = subprocess.Popen(  # noqa: S603 - a fixed argv list, no shell, the id validated by the caller
            argv,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            start_new_session=sys.platform != "win32",
        )
    except (OSError, ValueError):
        return CliResult(None, False, "")
    kept: list[bytes] = []
    reader = threading.Thread(target=_drain, args=(proc, kept), daemon=True)
    reader.start()
    timed_out = False
    try:
        returncode: int | None = proc.wait(timeout)
    except subprocess.TimeoutExpired:
        _kill(proc)
        proc.wait()
        returncode, timed_out = None, True
    reader.join(5)
    return CliResult(returncode, timed_out, b"".join(kept).decode("utf-8", "replace"))


def docker_restart(docker: str, container_id: str, timeout: float = DOCKER_TIMEOUT_S) -> CliResult:
    if not is_container_id(container_id):
        return CliResult(None, False, "")
    return run_argv([docker, "restart", container_id], timeout)
