"""Shared fixtures: golden BootUI payloads and the no-side-effects guard."""

import json
import logging
import os
import socket
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "bootui"
_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", ".pyright"}
_BLOCKED = ("connect", "create_connection", "getaddrinfo", "gethostbyname")


def golden(name: str) -> dict[str, Any]:
    """Load the sanitised BootUI payload ``tests/fixtures/bootui/<name>.json``."""
    # vulnerabilities.json: NOT_SCANNED scannedAt is null (contract §8, BootUI controller); its 0 is a capture artefact.
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


_PATH_PARAMS = {"file": "app.js"}  # a new path parameter fails collection until it gets a value here


def get_paths() -> list[str]:
    """Every sharpit GET path, read from the sample app's own sub-app route table, plus the bare mount path."""
    from examples.fastapi_sample.app import create_app
    from starlette.routing import Route

    from sharpit.fastapi.adapter import SharpitMount

    mount = next(r for r in create_app(show_banner=False).router.routes if isinstance(r, SharpitMount))
    assert all(isinstance(r, Route) for r in mount.routes)  # a Mount or WebSocketRoute would escape the sweep
    paths = ["/sharpit"]  # the bare mount path is the SharpitMount itself, not a sub-app route
    for route in mount.routes:
        if "GET" in (route.methods or ()):
            params = {name: _PATH_PARAMS[name] for name in route.param_convertors}
            paths.append("/sharpit" + route.path_format.format(**params))
    return paths


def _snapshot(root: Path) -> dict[str, tuple[int, int] | None]:
    """Every file and directory under root as path -> (mtime_ns, size); directories map to None."""
    snap: dict[str, tuple[int, int] | None] = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for name in dirs:
            snap[os.path.join(base, name)] = None
        for name in files:
            st = os.stat(os.path.join(base, name))
            snap[os.path.join(base, name)] = (st.st_mtime_ns, st.st_size)
    return snap


def _environ() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}  # pytest rewrites it per phase


def _levels() -> dict[str, int]:
    loggers = {n: lg.level for n, lg in logging.root.manager.loggerDict.items() if isinstance(lg, logging.Logger)}
    return {**loggers, "": logging.root.level}


class SideEffectGuard:
    """Blocks network access immediately; verify() reports filesystem, logger-level and environ changes."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.violations: list[str] = []
        self._originals: list[tuple[Any, str, Any]] = []
        self.cwd = Path.cwd()  # the test's cwd at setup; a later chdir does not move the snapshot
        self.rebaseline()

    def rebaseline(self) -> None:
        self.violations.clear()
        self._cwd_snap = _snapshot(self.cwd)
        self._state_snap = _snapshot(self.state_dir)
        self._levels = _levels()
        self._environ = _environ()

    def block_network(self) -> None:
        for owner, attr in ((socket.socket, "connect"), *((socket, n) for n in _BLOCKED[1:])):
            self._originals.append((owner, attr, getattr(owner, attr)))
            setattr(owner, attr, self._blocker(f"socket.{attr}"))

    def _blocker(self, what: str) -> Callable[..., Any]:
        def blocked(*_args: object, **_kwargs: object) -> Any:
            self.violations.append(what)
            raise AssertionError(f"side effect: {what} called")

        return blocked

    def unblock_network(self) -> None:
        for owner, attr, original in reversed(self._originals):
            setattr(owner, attr, original)
        self._originals.clear()

    def verify(self) -> None:
        problems = list(self.violations)
        for label, before, root in (("cwd", self._cwd_snap, self.cwd), ("state dir", self._state_snap, self.state_dir)):
            after = _snapshot(root)
            for path in sorted(before.keys() | after.keys()):
                if before.get(path, "absent") != after.get(path, "absent"):
                    problems.append(f"{label} changed: {path}")
        now = _levels()
        if any(now.get(n, 0) != self._levels.get(n, 0) for n in now.keys() | self._levels.keys()):
            problems.append("logger level changed")
        if _environ() != self._environ:
            problems.append("os.environ changed")
        assert not problems, "side effects detected: " + "; ".join(problems)


@pytest.fixture
def tmp_state_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("sharpit-state")


@pytest.fixture
def no_side_effects(tmp_state_dir: Path) -> Iterator[SideEffectGuard]:
    guard = SideEffectGuard(tmp_state_dir)
    guard.block_network()
    try:
        yield guard
    finally:
        guard.unblock_network()
    guard.verify()
