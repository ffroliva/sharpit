"""W8 D1: dev-services restart through the docker CLI. No test here runs a real ``docker``."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from sharpit.engine import devservices_cli
from sharpit.engine.devservices_cli import MAX_OUTPUT_BYTES, CliResult, docker_restart, resolve_docker, run_argv
from sharpit.engine.devservices_restart import RecordedService, restart
from sharpit.engine.masking import Exposure, Masker

CID = "0123456789ab" * 2
DOCKER = "/opt/fake/docker"
DISABLED = "Restart is disabled. Set SHARPIT_DEV_SERVICES_RESTART_ENABLED=true to allow it."
UNSUPPORTED = "Service does not support restart"
NOT_FOUND = "Service not found"
GENERIC = "Failed to restart service"
RESTARTED = "Service restarted. Already-created clients may need an application restart to reconnect."
TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0" * 2
EXE = "docker.exe" if os.name == "nt" else "docker"


class Spy:
    """Stands in for the resolver and the runner; ``calls`` stays empty when nothing may spawn."""

    def __init__(self, result: CliResult | Exception = CliResult(0, False, "")) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.result = result

    def resolve(self) -> str | None:
        self.calls.append(("resolve",))
        return DOCKER

    def run(self, docker: str, container_id: str) -> CliResult:
        self.calls.append((docker, container_id))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _find(recorded: dict[str, str | None]):
    return lambda sid: RecordedService(sid, recorded[sid]) if sid in recorded else None


def _go(spy: Spy, sid: str = "bean:pg", *, enabled: bool = True, recorded=None, mask=lambda t: t, resolve=None):
    return restart(
        sid,
        enabled=enabled,
        find=_find({"bean:pg": CID} if recorded is None else recorded),
        mask=mask,
        resolve=resolve or spy.resolve,
        run=spy.run,
    )


def test_restart_is_disabled_by_default_and_spawns_nothing() -> None:
    # ported: DevServicesControllerTests.restartIsDisabledByDefault
    spy = Spy()

    assert _go(spy, enabled=False) == (409, {"message": DISABLED})
    assert spy.calls == []


def test_restart_calls_docker_restart_once_with_the_snapshot_id() -> None:
    # ported: DevServicesControllerTests.restartCallsStopThenStartWhenExplicitlyEnabled
    spy = Spy()

    status, body = _go(spy)

    assert (status, body) == (200, {"id": "bean:pg", "status": "restarted", "message": RESTARTED})
    assert spy.calls == [("resolve",), (DOCKER, CID)]


def test_restart_returns_500_when_the_runner_exits_non_zero() -> None:
    # ported: DevServicesControllerTests.restartReturns500WhenStopThrows
    spy = Spy(CliResult(1, False, "Error response from daemon: boom"))

    assert _go(spy) == (500, {"message": "Error response from daemon: boom"})


def test_restart_failure_message_is_masked() -> None:
    masker = Masker(Exposure.FULL, True)
    spy = Spy(CliResult(1, False, f"login failed token={TOKEN}"))

    status, body = _go(spy, mask=masker.mask_text)

    assert status == 500
    assert TOKEN not in body["message"]


@pytest.mark.parametrize(
    "result",
    [CliResult(1, False, ""), CliResult(None, True, "partial"), OSError("no exec")],
    ids=["empty-output", "timeout", "spawn-error"],
)
def test_restart_failure_without_a_usable_message_is_generic(result: CliResult | Exception) -> None:
    assert _go(Spy(result)) == (500, {"message": GENERIC})


def test_restart_failure_with_nothing_shown_is_generic() -> None:
    # METADATA_ONLY masks every text to None
    assert _go(Spy(CliResult(1, False, "secret")), mask=lambda _t: None) == (500, {"message": GENERIC})


def test_restart_id_never_from_request() -> None:
    spy = Spy()

    assert _go(spy, sid=";rm -rf /") == (404, {"message": NOT_FOUND})
    assert spy.calls == []


def test_a_recorded_id_that_is_not_hex_never_reaches_argv() -> None:
    spy = Spy()

    assert _go(spy, recorded={"bean:pg": ";rm -rf /"}) == (409, {"message": UNSUPPORTED})
    assert spy.calls == [("resolve",)]


@pytest.mark.parametrize("recorded", [None, ""], ids=["none", "empty"])
def test_a_service_with_no_recorded_container_id_cannot_restart(recorded: str | None) -> None:
    spy = Spy()

    assert _go(spy, recorded={"bean:pg": recorded}) == (409, {"message": UNSUPPORTED})
    assert spy.calls == []


def test_no_docker_executable_cannot_restart() -> None:
    spy = Spy()

    assert _go(spy, resolve=lambda: None) == (409, {"message": UNSUPPORTED})
    assert spy.calls == []


def test_unknown_id_is_404_before_the_disabled_check() -> None:
    spy = Spy()

    assert _go(spy, sid="bean:nope", enabled=False) == (404, {"message": NOT_FOUND})
    assert spy.calls == []


def test_disabled_is_checked_before_docker_is_looked_up() -> None:
    spy = Spy()

    assert _go(spy, enabled=False, resolve=lambda: None) == (409, {"message": DISABLED})
    assert spy.calls == []


def test_docker_restart_refuses_a_non_hex_id() -> None:
    result = docker_restart(DOCKER, "abc; rm -rf /")

    assert (result.returncode, result.timed_out) == (None, False)


def test_docker_restart_argv_is_a_fixed_list(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[list[str], float]] = []

    def fake(argv: list[str], timeout: float) -> CliResult:
        seen.append((argv, timeout))
        return CliResult(0, False, "")

    monkeypatch.setattr(devservices_cli, "run_argv", fake)

    docker_restart(DOCKER, CID)

    assert seen == [([DOCKER, "restart", CID], 60.0)]


def test_resolve_docker_ignores_the_working_directory_and_relative_path_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / EXE).write_bytes(b"x")
    (tmp_path / EXE).chmod(0o755)
    monkeypatch.chdir(tmp_path)

    assert resolve_docker("") is None
    assert resolve_docker(os.pathsep.join([".", "bin"])) is None


def test_resolve_docker_returns_an_absolute_path_from_an_absolute_entry(tmp_path: Path) -> None:
    (tmp_path / EXE).write_bytes(b"x")
    (tmp_path / EXE).chmod(0o755)

    found = resolve_docker(os.pathsep.join(["relative", str(tmp_path)]))

    assert found == str(tmp_path / EXE)


def test_resolve_docker_never_picks_a_batch_file(tmp_path: Path) -> None:
    (tmp_path / "docker.cmd").write_bytes(b"x")
    (tmp_path / "docker.bat").write_bytes(b"x")

    assert resolve_docker(str(tmp_path)) is None


def test_timeout_is_sixty_seconds() -> None:
    assert devservices_cli.DOCKER_TIMEOUT_S == 60.0


def test_run_argv_kills_a_process_that_outlives_the_timeout() -> None:
    start = time.monotonic()

    result = run_argv([sys.executable, "-c", "import time; time.sleep(60)"], timeout=1.0)

    assert (result.returncode, result.timed_out) == (None, True)
    assert time.monotonic() - start < 20


def test_run_argv_bounds_output_and_keeps_draining() -> None:
    code = "import sys; sys.stdout.write('x' * 2_000_000)"

    result = run_argv([sys.executable, "-c", code], timeout=30.0)

    assert (result.returncode, result.timed_out) == (0, False)
    assert MAX_OUTPUT_BYTES == 16384
    assert len(result.output) == MAX_OUTPUT_BYTES


def test_run_argv_reports_a_non_zero_exit_with_its_output() -> None:
    code = "import sys; print('bad', file=sys.stderr); sys.exit(3)"

    result = run_argv([sys.executable, "-c", code], timeout=30.0)

    assert (result.returncode, result.timed_out, result.output.strip()) == (3, False, "bad")


def test_run_argv_does_not_read_the_parent_stdin() -> None:
    code = "import sys; print(repr(sys.stdin.read()))"

    result = run_argv([sys.executable, "-c", code], timeout=30.0)

    assert result.output.strip() == "''"


def test_run_argv_spawn_error_is_a_failed_result() -> None:
    result = run_argv([str(Path(sys.executable).parent / "no-such-binary-xyz")], timeout=5.0)

    assert (result.returncode, result.timed_out) == (None, False)
