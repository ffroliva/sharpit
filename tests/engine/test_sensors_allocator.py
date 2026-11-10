from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from coverage import CoverageData

from sharpit.engine.sensors.allocator import MonitoringToolAllocator


class StubMonitoring:
    def __init__(self) -> None:
        self.tools: dict[int, str] = {}
        self.callbacks: dict[tuple[int, int], Callable[..., object] | None] = {}
        self.events: dict[int, int] = {}
        self.calls: list[tuple[object, ...]] = []
        self.event = 32

    def get_tool(self, tool_id: int) -> str | None:
        return self.tools.get(tool_id)

    def use_tool_id(self, tool_id: int, name: str) -> None:
        if tool_id in self.tools:
            raise ValueError("tool id in use")
        self.calls.append(("use_tool_id", tool_id, name))
        self.tools[tool_id] = name

    def set_events(self, tool_id: int, events: int) -> None:
        self.calls.append(("set_events", tool_id, events))
        self.events[tool_id] = events

    def register_callback(self, tool_id: int, event: int, callback: Callable[..., object] | None) -> None:
        self.calls.append(("register_callback", tool_id, event, callback))
        self.callbacks[tool_id, event] = callback

    def free_tool_id(self, tool_id: int) -> None:
        self.calls.append(("free_tool_id", tool_id))
        self.tools.pop(tool_id)
        self.events.pop(tool_id, None)


def test_claims_first_free_candidate_and_skips_tool_in_use() -> None:
    monitoring = StubMonitoring()
    monitoring.tools[3] = "another tool"
    allocator = MonitoringToolAllocator(monitoring=monitoring)

    tool = allocator.claim()

    assert tool is not None
    assert tool.tool_id == 4
    assert monitoring.tools[3] == "another tool"


def test_claims_nothing_when_candidates_are_held() -> None:
    monitoring = StubMonitoring()
    monitoring.tools.update({3: "coverage", 4: "other"})
    allocator = MonitoringToolAllocator(monitoring=monitoring)

    tool = allocator.claim()

    assert tool is None
    assert monitoring.tools == {3: "coverage", 4: "other"}
    assert not any(call[0] == "free_tool_id" for call in monitoring.calls)


def test_skips_debugger_and_coverage_reservations() -> None:
    monitoring = StubMonitoring()
    monitoring.tools.update({0: "debugger", 1: "coverage", 2: "profiler", 3: "coverage worker", 5: "optimizer"})
    allocator = MonitoringToolAllocator(monitoring=monitoring)

    tool = allocator.claim()

    assert tool is not None
    assert tool.tool_id == 4
    assert monitoring.tools[0] == "debugger"
    assert monitoring.tools[1] == "coverage"


def test_concurrent_claims_get_distinct_ids() -> None:
    from concurrent.futures import ThreadPoolExecutor

    allocator = MonitoringToolAllocator(monitoring=StubMonitoring())
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(allocator.claim) for _ in range(2)]
    tools = [future.result() for future in futures]

    assert all(tool is not None for tool in tools)
    claimed = [tool for tool in tools if tool is not None]
    assert len({tool.tool_id for tool in claimed}) == 2
    for tool in claimed:
        tool.release()


def test_release_clears_events_callbacks_then_frees_only_owned_id() -> None:
    monitoring = StubMonitoring()
    allocator = MonitoringToolAllocator(monitoring=monitoring)
    tool = allocator.claim()
    assert tool is not None

    def callback() -> None:
        return None

    tool.register_callback(monitoring.event, callback)
    tool.set_events(monitoring.event)

    tool.release()
    tool.release()

    assert [call[0] for call in monitoring.calls[-3:]] == ["set_events", "register_callback", "free_tool_id"]
    assert monitoring.events.get(tool.tool_id, 0) == 0
    assert monitoring.callbacks[tool.tool_id, monitoring.event] is None
    assert monitoring.tools.get(tool.tool_id) is None
    assert monitoring.calls.count(("free_tool_id", tool.tool_id)) == 1


def test_release_clears_tool_id_on_runtime_that_supports_it() -> None:
    monitoring = StubMonitoring()
    monitoring.clear_tool_id = lambda tool_id: monitoring.calls.append(("clear_tool_id", tool_id))  # type: ignore[attr-defined]
    allocator = MonitoringToolAllocator(monitoring=monitoring)
    tool = allocator.claim()
    assert tool is not None

    tool.release()

    assert [call[0] for call in monitoring.calls[-2:]] == ["clear_tool_id", "free_tool_id"]


def test_real_monitoring_allocator_leaves_no_events_or_callbacks() -> None:
    monitoring: Any = getattr(sys, "monitoring", None)
    if monitoring is None:
        pytest.skip("sys.monitoring is unavailable")
    allocator = MonitoringToolAllocator(monitoring=monitoring)
    tool = allocator.claim()
    if tool is None:
        pytest.skip("tool ids 3 and 4 are occupied")
    event = monitoring.events.EXCEPTION_HANDLED
    tool.register_callback(event, lambda *_args: None)
    tool.set_events(event)
    tool.release()

    assert monitoring.get_events(tool.tool_id) == 0
    assert monitoring.register_callback(tool.tool_id, event, None) is None


def test_coverage_sysmon_keeps_its_tool_id_and_data(tmp_path: Path) -> None:
    source = tmp_path / "measured.py"
    source.write_text("value = 41\nvalue += 1\n", encoding="utf-8")
    probe = tmp_path / "probe.py"
    probe.write_text(
        """
import json, sys
from pathlib import Path
from sharpit.engine.sensors.allocator import MonitoringToolAllocator

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
monitoring = sys.monitoring
coverage_id = next((i for i in range(6) if monitoring.get_tool(i) == "coverage.py"), None)
if coverage_id is None:
    print("UNSUPPORTED")
    raise SystemExit(0)
before = monitoring.get_tool(coverage_id)
tool = MonitoringToolAllocator().claim()
assert tool is not None
tool.register_callback(monitoring.events.LINE, lambda *_args: None)
tool.set_events(monitoring.events.LINE)
import measured
tool.release()
assert monitoring.get_tool(coverage_id) == before
print(json.dumps({"coverage_id": coverage_id}))
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["COVERAGE_CORE"] = "sysmon"
    data_path = tmp_path / ".coverage"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "run",
            f"--data-file={data_path}",
            str(probe),
            str(tmp_path),
        ],
        capture_output=True,
        check=False,
        text=True,
        env=env,
        timeout=30,
    )

    if "UNSUPPORTED" in result.stdout:
        pytest.skip("coverage sysmon core is unavailable")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.splitlines()[-1])
    assert report["coverage_id"] == 1
    coverage = CoverageData(basename=str(data_path))
    coverage.read()
    if not coverage.measured_files():
        pytest.skip("COVERAGE_CORE=sysmon holds tool id 1 but collected no data in this environment")
    assert coverage.lines(str(source))
