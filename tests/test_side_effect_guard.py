"""The no-side-effects guard sees interpreter state and app-source reads (0.5.0 spec §4.4, PLAN Review Focus 6)."""

from __future__ import annotations

import gc
import sys
import tokenize
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from conftest import SideEffectGuard

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
