"""The Alembic child-process runner (W8 M1): bounded time, the tree killed on timeout, output captured."""

from __future__ import annotations

import sys
import time
from pathlib import Path
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


def test_runner_spawn_arguments_are_shell_free(tmp_path: Path, monkeypatch: Any):
    seen: dict[str, Any] = {}

    class Proc:
        pid = 0
        returncode = 0

        def communicate(self, timeout: float | None = None) -> tuple[bytes, None]:
            return b"ok", None

        def poll(self) -> int:
            return 0

        def kill(self) -> None: ...

    def popen(argv: Any, **kwargs: Any) -> Proc:
        seen.update(argv=argv, **kwargs)
        return Proc()

    result = alembic_cli.run_alembic(["a", "b"], str(tmp_path), 5.0, popen=popen)
    assert result.output == "ok"
    assert seen["argv"] == ["a", "b"]
    assert seen["shell"] is False
    assert seen["stdin"] is alembic_cli.subprocess.DEVNULL
    assert seen["stderr"] is alembic_cli.subprocess.STDOUT


def test_runner_has_a_hard_cap_of_ten_minutes():
    assert alembic_cli.TIMEOUT == 600.0
