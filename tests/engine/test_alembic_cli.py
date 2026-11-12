"""The Alembic child-process runner (W8 M1): bounded time, the tree killed on timeout, output captured."""

from __future__ import annotations

import io
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sharpit.engine.collectors import alembic_cli


def _run(code: str, tmp_path: Path, timeout: float = 20.0) -> alembic_cli.RunResult:
    return alembic_cli.run_alembic([sys.executable, "-c", code], str(tmp_path), timeout)


def test_runner_returns_the_exit_code_and_merged_output(tmp_path: Path):
    result = _run("import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)", tmp_path)
    assert result.returncode == 3
    assert "out" in result.output
    assert "err" in result.output
    assert result.failure is None


def test_runner_runs_in_the_given_directory(tmp_path: Path):
    result = _run("import os; print(os.getcwd())", tmp_path)
    assert Path(result.output.strip()).resolve() == tmp_path.resolve()


def test_runner_timeout_kills_the_child_and_reports_it(tmp_path: Path):
    marker = tmp_path / "survived"
    code = f"import time, pathlib; time.sleep(3); pathlib.Path({str(marker)!r}).write_text('x')"
    started = time.monotonic()
    result = _run(code, tmp_path, timeout=0.5)
    assert result.failure == "timeout"
    assert result.returncode is None
    assert time.monotonic() - started < 2.5
    time.sleep(3.5)
    assert not marker.exists()  # the child was killed, not abandoned


def test_runner_timeout_kills_a_grandchild_too(tmp_path: Path):
    marker = tmp_path / "grandchild"
    inner = f"import time, pathlib; time.sleep(3); pathlib.Path({str(marker)!r}).write_text('x')"
    code = f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {inner!r}]); time.sleep(30)"
    result = _run(code, tmp_path, timeout=1.0)
    assert result.failure == "timeout"
    time.sleep(4.5)
    assert not marker.exists()


def test_runner_reports_a_missing_program_without_raising(tmp_path: Path):
    result = alembic_cli.run_alembic([str(tmp_path / "no-such-python")], str(tmp_path), 5.0)
    assert result.failure == "error"
    assert result.returncode is None
    assert "no-such-python" in result.output or "OSError" in result.output or "Error" in result.output


class _Proc:
    pid = None  # no real process: the tree kill must be skipped
    returncode = 0

    def __init__(self, output: bytes = b"ok", wait_error: BaseException | None = None) -> None:
        self.stdout = io.BytesIO(output)
        self.output = output
        self.wait_error = wait_error
        self.waits: list[float | None] = []

    def communicate(self, **_kw: Any) -> tuple[bytes, None]:
        if self.wait_error is not None:
            raise self.wait_error
        return self.output, None

    def wait(self, timeout: float | None = None) -> int:
        self.waits.append(timeout)
        if self.wait_error is not None:
            raise self.wait_error
        return 0

    def poll(self) -> int:
        return 0

    def kill(self) -> None: ...


def _spawn(tmp_path: Path, proc: _Proc | None = None, platform: str | None = None, monkeypatch: Any = None) -> Any:
    seen: dict[str, Any] = {}

    def popen(argv: Any, **kwargs: Any) -> _Proc:
        seen.update(argv=argv, **kwargs)
        return proc or _Proc()

    if platform is not None:
        monkeypatch.setattr(alembic_cli, "sys", SimpleNamespace(platform=platform))
        monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    seen["result"] = alembic_cli.run_alembic(["a", "b"], str(tmp_path), 5.0, popen=popen)
    return seen


def test_runner_spawn_arguments_are_shell_free(tmp_path: Path):
    seen = _spawn(tmp_path)
    assert seen["result"].output == "ok"
    assert seen["argv"] == ["a", "b"]
    assert seen["shell"] is False
    assert seen["stdin"] is alembic_cli.subprocess.DEVNULL
    assert seen["stderr"] is alembic_cli.subprocess.STDOUT


def test_alembic_runner_uses_create_no_window_on_windows(tmp_path: Path, monkeypatch: Any):
    seen = _spawn(tmp_path, platform="win32", monkeypatch=monkeypatch)
    assert seen.get("creationflags") == 0x08000000
    assert "start_new_session" not in seen


def test_runner_starts_its_own_session_on_posix(tmp_path: Path, monkeypatch: Any):
    seen = _spawn(tmp_path, platform="linux", monkeypatch=monkeypatch)
    assert seen.get("start_new_session") is True
    assert "creationflags" not in seen


def test_runner_drops_the_cut_first_line_of_an_oversized_output(tmp_path: Path):
    cap = alembic_cli.MAX_OUTPUT_BYTES
    raw = b"SECRETFRAGMENT\n" + b"k" * (cap - 5)  # the last `cap` bytes start inside the first line
    seen = _spawn(tmp_path, _Proc(raw))
    assert "AGMENT" not in seen["result"].output
    assert seen["result"].output == "k" * (cap - 5)


def test_runner_output_stays_bounded_while_the_child_is_chatty(tmp_path: Path):
    code = "import sys\nfor _ in range(64): sys.stdout.buffer.write(b'x' * 1048576)"
    tracemalloc.start()
    try:
        result = _run(code, tmp_path, timeout=60.0)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert result.returncode == 0
    assert peak < 16 * 1024 * 1024


def test_runner_reaps_the_child_after_a_kill_whose_drain_times_out(tmp_path: Path):
    proc = _Proc(wait_error=subprocess.TimeoutExpired("a", 1))
    seen = _spawn(tmp_path, proc)
    assert seen["result"].failure == "timeout"
    assert len(proc.waits) == 2  # the time cap, then the post-kill reap: no zombie is left on POSIX
    assert proc.waits[-1] is not None
    assert proc.waits[-1] <= 30  # short, never the 600 s cap


def test_runner_has_a_hard_cap_of_ten_minutes():
    assert alembic_cli.TIMEOUT == 600.0
