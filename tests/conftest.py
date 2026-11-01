"""Shared fixtures: golden BootUI payloads and the no-side-effects guard."""

import ast
import asyncio
import json
import logging
import os
import socket
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine import sqla
from sharpit.engine.sources import sqlite

FIXTURES = Path(__file__).parent / "fixtures" / "bootui"
_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", ".pyright"}
_BLOCKED = ("connect", "create_connection", "getaddrinfo", "gethostbyname")


_SQLALCHEMY_MODULES = {"sqlalchemy", "aiosqlite", "alembic", "greenlet"}
NEEDS_SQLALCHEMY_MISSING = "imports {} at module level without pytestmark = pytest.mark.needs_sqlalchemy"


def sqlalchemy_imports_without_marker(source: str) -> list[str]:
    """Top-level imports of the optional SQLAlchemy stack in a module that lacks the ``needs_sqlalchemy`` mark.

    The no-sqlalchemy CI job runs ``-m "not needs_sqlalchemy"``: an unmarked module would fail at import there.
    """
    tree = ast.parse(source)
    found: list[str] = []
    marked = False
    for node in tree.body:
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] in _SQLALCHEMY_MODULES]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found += [node.module] if node.module.split(".")[0] in _SQLALCHEMY_MODULES else []
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
        ):
            marked = "needs_sqlalchemy" in ast.unparse(node.value)
    return [] if marked else found


def pytest_pycollect_makemodule(module_path: Path, parent: Any) -> None:
    del parent
    found = sqlalchemy_imports_without_marker(module_path.read_text(encoding="utf-8"))
    if found:
        pytest.fail(f"{module_path.name} {NEEDS_SQLALCHEMY_MISSING.format(', '.join(found))}", pytrace=False)


TIMING_MODULES = ("test_capture_overhead.py", "test_sql_trace_overhead.py")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Timing budgets run last: xdist hands out tests in this order, so they meet a draining pool, not 22 busy ones."""
    items.sort(key=lambda item: item.path.name in TIMING_MODULES)  # stable: everything else keeps its order


def golden(name: str) -> dict[str, Any]:
    """Load the sanitised BootUI payload ``tests/fixtures/bootui/<name>.json``."""
    # vulnerabilities.json: NOT_SCANNED scannedAt is null (contract §8, BootUI controller); its 0 is a capture artefact.
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


_PATH_PARAMS = {
    "file": "app.js",
    "id": "0123456789abcdef",
    "name": "nope",  # an unknown pool name (404)
    "rule_id": "RAPI-MAP-001",  # rest-api violations without a scanId: 400
}  # a new path parameter fails collection until it gets a value here


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
            problems.extend(
                f"{label} changed: {path}"
                for path in sorted(before.keys() | after.keys())
                if before.get(path, "absent") != after.get(path, "absent")
            )
        now = _levels()
        if any(now.get(n, 0) != self._levels.get(n, 0) for n in now.keys() | self._levels.keys()):
            problems.append("logger level changed")
        if _environ() != self._environ:
            problems.append("os.environ changed")
        assert not problems, "side effects detected: " + "; ".join(problems)


@pytest.fixture(autouse=True)
def _no_sqlite3_patch_leak(request: pytest.FixtureRequest) -> Iterator[None]:
    """sqlite3 source tests detach what they attach: a leak fails them. Elsewhere install() without a lifespan leaks.

    shortcut: 230+ tests install an app and never run its shutdown (a supported use), so the leak is only asserted
    for the files that exercise the source itself; upgrade if those tests get a shared fixture that uninstalls.
    """
    sqlite.detach_all()
    sqla.detach_all()  # install() without shutdown leaves contexts; 2+ make routing outside a request ambiguous
    yield
    leaked = sqlite.is_attached()
    sqlite.detach_all()
    strict = any(word in request.node.path.name for word in ("sqlite", "dispatch", "sources"))
    assert not (leaked and strict), (
        "the test left sqlite3.connect patched; detach it (uninstall_capture / sqlite.detach)"
    )


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


# --- SSE streams held open on the ASGI app (TestClient buffers a body until the stream ends) -----------------------


def stream_scope(path: str) -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"localhost")],
        "client": ("127.0.0.1", 50000),
        "server": ("localhost", 80),
    }


class OpenStream:
    """One stream held open on the app (call inside a running loop): ``started`` once its response head went out."""

    def __init__(self, app: Any, path: str) -> None:
        self.sent: list[dict[str, Any]] = []
        self.started = asyncio.Event()

        async def receive() -> dict[str, Any]:
            await asyncio.Event().wait()
            raise AssertionError  # pragma: no cover

        async def send(message: dict[str, Any]) -> None:
            self.sent.append(message)
            if message["type"] == "http.response.start":
                self.started.set()

        self.task = asyncio.ensure_future(app(stream_scope(path), receive, send))

    @property
    def status(self) -> int:
        return self.sent[0]["status"]

    @property
    def body(self) -> str:
        return b"".join(m.get("body", b"") for m in self.sent).decode()
