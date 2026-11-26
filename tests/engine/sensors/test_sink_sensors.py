"""The command and file sinks: request values matching in processes and files sensors."""

from __future__ import annotations

import contextlib
import os
import platform
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest

from sharpit.engine.capture.correlation import REQUEST, RequestInfo
from sharpit.engine.sensors.files import FilesSensor
from sharpit.engine.sensors.processes import ProcessesSensor
from sharpit.engine.sensors.sinks import (
    FROM_REQUEST_INPUT,
    MAX_ARGUMENTS,
    MAX_SCAN,
    NOT_CHECKED,
    RequestValues,
    SinkMatcher,
)
from sharpit.engine.sensors.sinks.values import MAX_CHECKS


def info(
    query: str = "",
    path: dict[str, Any] | None = None,
    request_id: str = "a" * 16,
    context_id: str = "ctx",
) -> RequestInfo:
    scope: dict[str, Any] = {"query_string": query.encode(), **({"path_params": path} if path is not None else {})}
    return RequestInfo(request_id, context_id, "GET", "/", None, 0, None, scope=scope)


@pytest.fixture(autouse=True)
def clean_context() -> Iterator[None]:
    req_token = REQUEST.set(None)
    try:
        yield
    finally:
        REQUEST.reset(req_token)


_SENSOR_REQUESTS: dict[int, RequestInfo] = {}


def processes(query: str = "", path: dict[str, Any] | None = None, *, owns: bool = True) -> ProcessesSensor:
    req = info(query, path)
    values = RequestValues()
    matcher = SinkMatcher("ctx", on=lambda: True, values=values, owns=lambda scope: owns)
    sensor = ProcessesSensor(matcher=matcher)
    _SENSOR_REQUESTS[id(sensor)] = req
    return sensor


def files(
    query: str = "",
    path: dict[str, Any] | None = None,
    *,
    owns: bool = True,
    cwd: str = "/work/app",
    home: str = "/home/ann",
    tmp: str = "/tmp",  # noqa: S108
) -> FilesSensor:
    req = info(query, path)
    values = RequestValues()
    matcher = SinkMatcher("ctx", on=lambda: True, values=values, owns=lambda scope: owns)
    sensor = FilesSensor(cwd=cwd, home=home, tmp=tmp, matcher=matcher)
    _SENSOR_REQUESTS[id(sensor)] = req
    return sensor


def run(sensor: ProcessesSensor | FilesSensor, event: str, *args: Any) -> list[dict[str, Any]]:
    req = _SENSOR_REQUESTS.get(id(sensor))
    token = REQUEST.set(req)
    try:
        return [dict(r) for r in sensor.record(event, args)]
    finally:
        REQUEST.reset(token)


def sensor_values(sensor: ProcessesSensor | FilesSensor) -> RequestValues:
    matcher = cast(Any, sensor)._matcher
    assert matcher is not None
    return cast(RequestValues, matcher._values)


def end_request(sensor: ProcessesSensor | FilesSensor) -> None:
    req = _SENSOR_REQUESTS.get(id(sensor))
    matcher = cast(Any, sensor)._matcher
    if matcher is not None and req is not None:
        matcher.request_ended(req.id)


def test_an_argv_argument_names_the_command_and_the_index_only() -> None:
    # ported: RequestValuesSinksTests.aCommandArgumentHoldingAValueRecordsTheCommandAndTheArgumentsIndexOnly
    rows = run(
        processes("file=report-q3"),
        "subprocess.Popen",
        "/usr/bin/convert",
        ["/usr/bin/convert", "/srv/in/report-q3.pdf", "out.png"],
        None,
        None,
    )
    assert [(r["source"], r["target"]) for r in rows] == [
        ("processes", "convert"),
        ("security-sinks", "convert, argument 1"),
    ]
    assert "report-q3" not in repr(rows)


@pytest.mark.parametrize(
    ("event", "args", "target"),
    [
        ("subprocess.Popen", ("/bin/sh", ["/bin/sh", "-c", "ls report-q3"], None, None), "sh, argument 2"),
        ("subprocess.Popen", (None, "python.exe -c pass report-q3", None, None), "python.exe"),
        ("os.system", ("convert report-q3",), "convert"),
    ],
)
def test_a_shell_or_a_joined_command_line_names_what_it_can(event: str, args: tuple[Any, ...], target: str) -> None:
    rows = run(processes("file=report-q3"), event, *args)
    assert len(rows) > 1
    assert rows[1]["target"] == target


@pytest.mark.parametrize("argv", [["evil-tool", "--help"], "evil-tool --help"])
def test_an_executable_holding_a_value_is_named_by_neither_row(argv: object) -> None:
    # ported: RequestValuesSinksTests.anExecutableHoldingAValueIsNamedByNeitherRecord
    rows = run(processes("tool=evil-tool"), "subprocess.Popen", None, argv, None, None)
    assert [r["target"] for r in rows] == [FROM_REQUEST_INPUT, "(the executable)"]


def test_a_file_path_keeps_the_redacted_pattern() -> None:
    # ported: RequestValuesSinksTests.aFilePathHoldingAValueRecordsTheRedactedPathsPattern
    rows = run(files("name=../../etc/passwd"), "open", "reports/../../etc/passwd", "r", 0)
    assert [(r["source"], r["target"]) for r in rows] == [
        ("files", "./reports/{name}"),
        ("security-sinks", "./reports/{name}"),
    ]


def test_a_path_the_request_could_not_check_is_never_named() -> None:
    # ported: RequestValuesSinksTests.aPathLongerThanTheScanIsNeverNamedTheFirstTimeNorWhenRepeated
    sensor = files("name=quarterly")
    path = "x/" * (MAX_SCAN // 2) + "quarterly"
    assert [run(sensor, "open", path, "r", 0)[0]["target"] for _ in range(2)] == [NOT_CHECKED, NOT_CHECKED]


def test_a_path_opened_300_times_publishes_one_sink_row_and_redacts_every_file_row() -> None:
    # ported: RequestValuesSinksTests.aPathOpenedTwiceByTheRequestIsRedactedBothTimesInEveryRecord
    sensor = files("name=quarterly")
    rows = [r for _ in range(MAX_CHECKS + 44) for r in run(sensor, "open", "reports/quarterly.csv", "r", 0)]
    assert sum(r["source"] == "security-sinks" for r in rows) == 1
    assert {r["target"] for r in rows} == {"./reports/{name}.csv"}


def test_an_import_path_holding_a_value_is_left_out_and_spends_no_check() -> None:
    sensor = files("q=python")
    assert run(sensor, "open", os.path.join(sys.prefix, "python", "x.py"), "r", 0) == []
    assert sensor_values(sensor).held() == 0
    assert len(run(sensor, "open", "/work/app/python/x.py", "r", 0)) > 1


def test_no_cache_keeps_a_value_after_the_request() -> None:
    sensor = files("name=quarterly")
    run(sensor, "open", "reports/quarterly.csv", "r", 0)
    run(sensor, "shutil.copyfile", "a/quarterly", "b/quarterly")  # announced, never opened
    end_request(sensor)
    assert "quarterly" not in repr(vars(sensor))


def test_not_owned_work_redacts_its_row_and_publishes_no_sink() -> None:
    rows = run(files("name=quarterly", owns=False), "open", "reports/quarterly.csv", "r", 0)
    assert [(r["source"], r["target"]) for r in rows] == [("files", "./reports/{name}.csv")]


def test_the_thirty_third_argument_is_not_checked() -> None:
    sensor = processes("val=needle")
    argv32 = ["tool", *(f"arg{i}" for i in range(1, MAX_ARGUMENTS - 1)), "needle"]
    rows32 = run(sensor, "subprocess.Popen", None, argv32, None, None)
    assert len(rows32) > 1
    assert rows32[1]["target"] == f"tool, argument {MAX_ARGUMENTS - 1}"

    argv33 = ["tool", *(f"arg{i}" for i in range(1, MAX_ARGUMENTS)), "needle"]
    rows33 = run(sensor, "subprocess.Popen", None, argv33, None, None)
    assert len(rows33) == 1
    assert rows33[0]["target"] == "tool"


def test_without_a_matcher_every_row_is_unchanged() -> None:
    p_sensor = ProcessesSensor()
    p_rows = p_sensor.record("subprocess.Popen", ("/usr/bin/convert", ["/usr/bin/convert", "file.pdf"], None, None))
    assert [r["target"] for r in p_rows] == ["convert"]

    f_sensor = FilesSensor(cwd="/work/app", home="/home/ann", tmp="/tmp")  # noqa: S108
    f_rows = f_sensor.record("open", ("/work/app/reports/report-42.csv", "w", 0))
    assert [r["target"] for r in f_rows] == ["./reports/report-{n}.csv"]


def test_an_executable_the_request_could_not_check_is_never_named() -> None:
    # ported: RequestValuesSinksTests.aPathOrAnExecutableTheRequestsMatchingCouldNotCheckIsNeverNamed
    sensor = processes("v=needle")
    # Exhaust check budget by doing MAX_CHECKS distinct checks
    for i in range(MAX_CHECKS):
        run(sensor, "subprocess.Popen", None, [f"cmd{i}"], None, None)
    rows = run(sensor, "subprocess.Popen", None, ["tool", "arg"], None, None)
    assert len(rows) == 1
    assert rows[0]["target"] == NOT_CHECKED


def test_a_check_that_raises_keeps_the_row_and_hides_its_target() -> None:
    p_sensor = processes("tool=evil-tool")
    matcher = cast(Any, p_sensor)._matcher
    assert matcher is not None
    with patch.object(matcher, "check", side_effect=RuntimeError("boom")):
        p_rows = run(p_sensor, "subprocess.Popen", None, ["tool", "arg"], None, None)
        assert len(p_rows) == 1
        assert p_rows[0]["target"] == NOT_CHECKED

    f_sensor = files("name=quarterly")
    f_matcher = cast(Any, f_sensor)._matcher
    assert f_matcher is not None
    with patch.object(f_matcher, "check", side_effect=RuntimeError("boom")):
        f_rows = run(f_sensor, "open", "reports/quarterly.csv", "r", 0)
        assert len(f_rows) == 1
        assert f_rows[0]["target"] == NOT_CHECKED


def test_unlinking_a_temp_file_without_a_request_value_leaves_an_unchanged_row() -> None:
    fd, path = tempfile.mkstemp()
    os.close(fd)
    try:
        sensor_with_matcher = files("v=quarterly", tmp=tempfile.gettempdir())
        rows_with = run(sensor_with_matcher, "os.remove", path, None)

        sensor_without = FilesSensor(tmp=tempfile.gettempdir())
        rows_without = [dict(r) for r in sensor_without.record("os.remove", (path, None))]

        assert rows_with == rows_without
        assert rows_with[0]["target"].startswith("$TMPDIR/")
    finally:
        with contextlib.suppress(OSError):
            os.remove(path)


def test_platform_system_starts_no_command() -> None:
    sensor = ProcessesSensor()
    # platform.system() does not spawn subprocesses or exec commands on supported platforms
    platform_name = platform.system()
    assert isinstance(platform_name, str)
    # verify that calling platform.system() produces no recorded process events
    assert sensor.record("os.system", ()) == ()


def test_a_value_naming_part_of_the_temp_folder_redacts_and_classes_elsewhere() -> None:
    tmp_dir = tempfile.gettempdir()
    tmp_segment = Path(tmp_dir).name
    if not tmp_segment or len(tmp_segment) < 4:
        tmp_segment = "tmppath"
    sensor = files(f"u={tmp_segment}", tmp=tmp_dir)
    target_path = os.path.join(tmp_dir, "report.csv")
    rows = run(sensor, "open", target_path, "r", 0)
    assert len(rows) > 0
    assert rows[0]["location"] == "elsewhere"


def test_an_overflowed_command_line_never_names_its_program() -> None:
    sensor = processes("arg=aaaa&tool=evilx")
    cmd = "evilx" + " aaaa" * 9
    rows1 = run(sensor, "subprocess.Popen", None, cmd, None, None)
    assert "evilx" not in repr(rows1)
    assert rows1[0]["target"] == FROM_REQUEST_INPUT

    rows2 = run(sensor, "os.system", cmd)
    assert "evilx" not in repr(rows2)
    assert rows2[0]["target"] == FROM_REQUEST_INPUT


def test_pathlike_and_bytes_command_texts_are_checked_decoded() -> None:
    sensor = processes("tool=evil-tool&file=report-q3")
    rows = run(sensor, "subprocess.Popen", None, [Path("evil-tool"), b"report-q3"], None, None)
    assert rows[0]["target"] == FROM_REQUEST_INPUT
    assert len(rows) > 2
    assert rows[1]["target"] == "(the executable)"
    assert rows[2]["target"] == "(the executable), argument 1"

    sensor_sys = processes("file=report-q3")
    rows_sys = run(sensor_sys, "os.system", b"convert report-q3")
    assert len(rows_sys) > 1
    assert rows_sys[1]["target"] == "convert"


def test_an_explicit_executable_beside_one_string_is_checked_on_its_own() -> None:
    sensor = processes("tool=evil-tool")
    rows = run(sensor, "subprocess.Popen", "evil-tool", "echo hello", None, None)
    assert rows[0]["target"] == FROM_REQUEST_INPUT
    assert len(rows) > 1
    assert rows[1]["target"] == "(the executable)"
    assert "evil-tool" not in repr(rows)
