"""The no-side-effects guard sees interpreter state and app-source reads (0.5.0 spec §4.4, PLAN Review Focus 6)."""

from __future__ import annotations

import gc
import linecache
import os
import sys
import threading
import tokenize
import tracemalloc
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import test_safety_matrix as matrix
from conftest import SideEffectGuard, leaked_runtime_spies
from sharpit.engine import mcp

Change = Callable[[Path], Callable[[], None]]  # makes one change (given the app root), returns its undo


def _trace(*_args: object) -> None:
    return None


def _start_tracemalloc(_root: Path) -> Callable[[], None]:
    was = tracemalloc.is_tracing()
    tracemalloc.start()
    return (lambda: None) if was else tracemalloc.stop


def _append_gc_callback(_root: Path) -> Callable[[], None]:
    gc.callbacks.append(_trace)
    return lambda: gc.callbacks.remove(_trace)


def _set_gc_threshold(_root: Path) -> Callable[[], None]:
    saved = gc.get_threshold()
    gc.set_threshold(1)
    return lambda: gc.set_threshold(*saved)


def _disable_gc(_root: Path) -> Callable[[], None]:
    was = gc.isenabled()
    gc.disable()
    return gc.enable if was else (lambda: None)


def _settrace(_root: Path) -> Callable[[], None]:
    saved = sys.gettrace()
    sys.settrace(_trace)
    return lambda: sys.settrace(saved)


def _setprofile(_root: Path) -> Callable[[], None]:
    saved = sys.getprofile()
    sys.setprofile(_trace)
    return lambda: sys.setprofile(saved)


def _use_monitoring_tool(_root: Path) -> Callable[[], None]:
    free = next(i for i in range(6) if sys.monitoring.get_tool(i) is None)
    sys.monitoring.use_tool_id(free, "x")
    return lambda: sys.monitoring.free_tool_id(free)


def _open_source(root: Path) -> Callable[[], None]:
    with open(root / "main.py", encoding="utf-8") as handle:  # noqa: PTH123 - the builtin is what is spied on
        handle.read()
    return lambda: None


def _read_text_source(root: Path) -> Callable[[], None]:
    (root / "main.py").read_text(encoding="utf-8")
    return lambda: None


def _tokenize_open_source(root: Path) -> Callable[[], None]:
    with tokenize.open(root / "main.py") as handle:  # how an AST scanner reads a module
        handle.read()
    return lambda: None


CHANGES: dict[str, Change] = {
    "tracemalloc.start": _start_tracemalloc,
    "gc.callbacks": _append_gc_callback,
    "gc.set_threshold": _set_gc_threshold,
    "gc.disable": _disable_gc,
    "sys.settrace": _settrace,
    "sys.setprofile": _setprofile,
    "sys.monitoring.use_tool_id": _use_monitoring_tool,
    "open app source": _open_source,
    "read_text app source": _read_text_source,
    "tokenize.open app source": _tokenize_open_source,
}


def _app_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)  # the guard snapshots the cwd: keep it small and outside the app
    root = tmp_path / "app"
    root.mkdir()
    (root / "main.py").write_text("import os\nKEY = os.getenv('KEY')\n", encoding="utf-8")
    return root


def _verify_error(guard: SideEffectGuard) -> str | None:
    try:
        guard.verify()
    except AssertionError as error:
        return str(error)
    return None


@pytest.mark.parametrize("change", list(CHANGES))
def test_side_effect_guard_catches_interpreter_state(
    change: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a fake GET handler making one change; the guard watches the app root, as a lane's GET test does
    root = _app_root(tmp_path, monkeypatch)
    guard = SideEffectGuard(tmp_path / "state")
    guard.watch_sources(root)
    undo: Callable[[], None] = lambda: None  # noqa: E731
    try:
        undo = CHANGES[change](root)
        error = _verify_error(guard)
    finally:
        undo()
        guard.unwatch_sources()

    assert error is not None, f"verify() did not report {change}"


def test_side_effect_guard_allows_config_getenv_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # spec §14: config's lazy getenv scan on its first GET is the one declared exemption from "no app source read"
    root = _app_root(tmp_path, monkeypatch)
    scan: dict[str, Any] = {"__name__": "sharpit.engine.collectors.config.getenv_scan"}
    exec("def read(path):\n    return path.read_text(encoding='utf-8')\n", scan)  # noqa: S102 - a frame in config
    guard = SideEffectGuard(tmp_path / "state")
    guard.watch_sources(root)
    try:
        scan["read"](root / "main.py")
        error = _verify_error(guard)
    finally:
        guard.unwatch_sources()

    assert error is None


def test_side_effect_guard_ignores_reads_outside_the_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _app_root(tmp_path, monkeypatch)
    (tmp_path / "fixture.json").write_text("{}", encoding="utf-8")
    guard = SideEffectGuard(tmp_path / "state")
    guard.watch_sources(root)
    try:
        (tmp_path / "fixture.json").read_text(encoding="utf-8")
        error = _verify_error(guard)
    finally:
        guard.unwatch_sources()

    assert error is None


def test_side_effect_guard_reports_sharpit_monitoring_call_without_swallowing_it(tmp_path: Path) -> None:
    guard = SideEffectGuard(tmp_path / "state")
    guard.block_network()
    source = Path(__file__).resolve().parents[1] / "src" / "sharpit" / "probe.py"
    try:
        code = compile("import sys\nsys.monitoring.set_events(5, 0)", str(source), "exec")
        with pytest.raises(ValueError, match="tool"):
            exec(code)  # noqa: S102
    finally:
        guard.unblock_network()
        guard.restore_runtime_state()

    assert guard.violations == ["sys.monitoring.set_events"]


def test_side_effect_guard_sees_a_read_through_a_warm_linecache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # fix round 1: the host's FastAPI reads its endpoint's source (inspect.getsourcelines) on the first request, so
    # linecache is warm before the sweep watches; a later inspect.getsource by sharpit must still be reported
    root = _app_root(tmp_path, monkeypatch)
    linecache.getlines(str(root / "main.py"))  # the host warmed the cache
    guard = SideEffectGuard(tmp_path / "state")
    guard.watch_sources(root)
    try:
        linecache.getlines(str(root / "main.py"))  # what inspect.getsource does
        error = _verify_error(guard)
    finally:
        guard.unwatch_sources()
        linecache.clearcache()

    assert error is not None, "a read served by a warm linecache was not reported"


def test_side_effect_guard_watches_while_another_thread_fills_linecache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # CI run 42459653867 (test shard 3.12 1/5): watch_sources walked the live linecache.cache while another thread
    # wrote it (FastAPI's inspect.getsourcelines on a route's first request runs on the TestClient portal thread):
    # "RuntimeError: dictionary changed size during iteration". Forced interleave: the write lands mid-walk.
    root = _app_root(tmp_path, monkeypatch)
    linecache.getlines(str(root / "main.py"))  # a warm entry: the walk has a key to visit
    other = tmp_path / "portal.py"  # outside root: the guard has no reason to evict it
    other.write_text("x = 1\n", encoding="utf-8")
    realpath = os.path.realpath

    def realpath_while_another_thread_writes(path: Any, *args: Any, **kwargs: Any) -> Any:
        if path in linecache.cache and str(other) not in linecache.cache:
            writer = threading.Thread(target=linecache.getlines, args=(str(other),))
            writer.start()
            writer.join()
        return realpath(path, *args, **kwargs)

    monkeypatch.setattr(os.path, "realpath", realpath_while_another_thread_writes)
    guard = SideEffectGuard(tmp_path / "state")
    error: RuntimeError | None = None
    try:
        guard.watch_sources(root)
    except RuntimeError as raised:
        error = raised
    finally:
        guard.unwatch_sources()
        linecache.clearcache()

    assert error is None, f"watch_sources raced a concurrent linecache write: {error}"


# --- the shared sweeps watch the sample app's source (0.5.0 spec §4.4: every lane's no_side_effects test inherits it)

SAMPLE_SOURCE = Path(__file__).resolve().parents[1] / "examples" / "fastapi_sample" / "app.py"


def _read_sample_source() -> None:
    SAMPLE_SOURCE.read_text(encoding="utf-8")


def _sweep_error(
    sweep: Callable[[SideEffectGuard], None], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> str | None:
    """One case of a shared sweep under a fresh guard, set up and torn down as the no_side_effects fixture does."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)  # the guard snapshots the cwd: keep it small
    (tmp_path / "state").mkdir()
    guard = SideEffectGuard(tmp_path / "state")
    guard.block_network()
    try:
        sweep(guard)
    finally:
        guard.unblock_network()
        guard.unwatch_sources()
        guard.restore_runtime_state()
    return _verify_error(guard)


def test_sweep_harness_leaves_no_monitoring_spy_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # PR #124 CI: a spy left by this harness made the swallowed-exception budget see 0 of 1000 callbacks
    originals = {name: getattr(sys.monitoring, name) for name in ("use_tool_id", "set_events", "register_callback")}

    _sweep_error(lambda _guard: None, tmp_path, monkeypatch)

    assert sys.monitoring.use_tool_id is originals["use_tool_id"]
    assert sys.monitoring.set_events is originals["set_events"]
    assert sys.monitoring.register_callback is originals["register_callback"]


def test_get_sweep_reports_an_app_source_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # review F5a-harness #1: a GET that reads the app's source fails the shared GET sweep
    tool_info = mcp.tool_info

    def reading_tool_info(*args: Any) -> dict[str, Any]:  # what GET /mcp-server runs per listed tool
        _read_sample_source()
        return tool_info(*args)

    monkeypatch.setattr(mcp, "tool_info", reading_tool_info)
    path = "/sharpit/api/mcp-server"

    error = _sweep_error(lambda g: matrix.test_every_get_no_side_effects(g, path, "plain"), tmp_path, monkeypatch)

    assert error is not None, "the GET sweep did not report an app source read"
    assert "app source read" in error


def test_mcp_sweep_reports_an_app_source_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # review F5a-harness #1: an MCP read tool that reads the app's source fails the shared MCP sweep
    def reading(tool: Any) -> Any:
        def handler(call: Any, arguments: dict[str, Any]) -> dict[str, Any]:
            _read_sample_source()
            return tool.handler(call, arguments)

        return replace(tool, handler=handler)

    monkeypatch.setattr(mcp, "TOOLS", [reading(t) if t.name == "get_loggers" else t for t in mcp.TOOLS])

    error = _sweep_error(
        lambda g: matrix.test_every_mcp_tool_no_side_effects(g, "get_loggers", "plain"), tmp_path, monkeypatch
    )

    assert error is not None, "the MCP sweep did not report an app source read"
    assert "app source read" in error


def test_a_left_behind_monitoring_spy_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    # PR #124 CI: a leaked spy showed up only as a budget miss in a later test; name it at the leaking test instead
    monkeypatch.setattr(sys.monitoring, "set_events", lambda *_args: None)

    assert leaked_runtime_spies() == ["sys.monitoring.set_events"]


def test_another_workers_pytest_cache_staging_dir_is_not_a_side_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # sbx K9 and P-http: a parallel xdist worker's cache writer staged pytest-cache-files-* in the shared cwd mid-test
    def stage(_guard: SideEffectGuard) -> None:
        staged = Path.cwd() / "pytest-cache-files-a9zm7kpp"
        staged.mkdir()
        (staged / "lastfailed").write_text("{}", encoding="utf-8")

    assert _sweep_error(stage, tmp_path, monkeypatch) is None


def test_a_file_written_in_the_cwd_is_still_a_side_effect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # the control: only pytest's own staging dir is ignored, never a write the code under test makes
    error = _sweep_error(
        lambda _guard: (Path.cwd() / "pytest-cache.json").write_text("{}", encoding="utf-8"), tmp_path, monkeypatch
    )
    assert error is not None
    assert "cwd changed" in error


@pytest.mark.parametrize("name", ["pytest-cache-other-x", "nested/pytest-cache-files-x"])
def test_a_directory_made_in_the_cwd_is_still_a_side_effect(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the skip is exactly pytest's staging prefix at the top of the cwd, nothing near it
    error = _sweep_error(lambda _guard: (Path.cwd() / name).mkdir(parents=True), tmp_path, monkeypatch)
    assert error is not None
    assert "cwd changed" in error
