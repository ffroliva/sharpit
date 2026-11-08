"""Shared fixtures: golden BootUI payloads and the no-side-effects guard."""

import ast
import asyncio
import builtins
import gc
import importlib.util
import io
import json
import linecache
import logging
import os
import socket
import sys
import tempfile
import tokenize
import tracemalloc
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

# Hypothesis caches constants under the working directory, and `no_side_effects` reads a file written there as a read
# that wrote one. Set before its import, so no run writes into the tree.
os.environ.setdefault("HYPOTHESIS_STORAGE_DIRECTORY", str(Path(tempfile.gettempdir()) / "sharpit-hypothesis"))

from hypothesis import settings  # noqa: E402

from sharpit.engine import sqla
from sharpit.engine.capture import transactions
from sharpit.engine.sources import sqlite
from sharpit.engine.sqltext.identity import load_key

pytest_plugins = ["pytester", "_shard"]  # _shard: SHARPIT_SHARD=i/n, the CI shards (tests/_shard.py)

# The property tests run the same examples on every run and every shard, and write no example database: a failure seen
# once is seen again, and a slow runner is not a failure (design section 8).
settings.register_profile("sharpit", derandomize=True, deadline=None, database=None, print_blob=False)
settings.load_profile("sharpit")

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


def needs_sqlalchemy_marker(source: str) -> bool:
    return any(
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets)
        and "needs_sqlalchemy" in ast.unparse(node.value)
        for node in ast.parse(source).body
    )


def pytest_pycollect_makemodule(module_path: Path, parent: Any) -> None:
    del parent
    found = sqlalchemy_imports_without_marker(module_path.read_text(encoding="utf-8"))
    if found:
        pytest.fail(f"{module_path.name} {NEEDS_SQLALCHEMY_MISSING.format(', '.join(found))}", pytrace=False)


TIMING_MODULES = (
    "test_capture_overhead.py",
    "test_mask_error_overhead.py",  # masking redesign, Task 5
    "test_n_plus_one_overhead.py",
    "test_sql_trace_overhead.py",
    "test_sqlite_overhead.py",
    "test_swallowed_overhead.py",
    "test_traces_overhead.py",
    "test_transactions_overhead.py",  # lane R-transactions
    "test_sink_overhead.py",  # lane P-sink-mask-memo
)  # every module that times a budget (tests/test_overhead_harness.py keeps this complete)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--live", action="store_true", help="collect tests/live: real database servers (the CI live job)")


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    """Without ``--live`` the live profile is not collected, so a default run has no live test and nothing to skip."""
    live = collection_path.name == "live" and collection_path.parent.name == "tests"
    if live and not config.getoption("--live"):
        return True
    if (
        importlib.util.find_spec("sqlalchemy") is None
        and collection_path.suffix == ".py"
        and needs_sqlalchemy_marker(collection_path.read_text(encoding="utf-8"))
    ):
        return True
    return None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Timing budgets run last: xdist hands out tests in this order, so they meet a draining pool, not 22 busy ones."""
    if not config.getoption("--live"):  # pytest does not ask pytest_ignore_collect for a path named on the command line
        live = [i for i in items if "live" in i.path.parts[-2:-1] and i.path.parent.parent.name == "tests"]
        config.hook.pytest_deselected(items=live)
        items[:] = [i for i in items if i not in live]
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
    from safety import load, sample_params

    lanes = load()  # a lane's PATH_PARAMS apply to that lane's own routes only
    paths = ["/sharpit"]  # the bare mount path is the SharpitMount itself, not a sub-app route
    for route in mount.routes:
        if "GET" in (route.methods or ()):
            samples = sample_params("/sharpit" + route.path_format, lanes, _PATH_PARAMS)
            params = {name: samples[name] for name in route.param_convertors}
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


def _interpreter_state() -> dict[str, object]:
    """What a read must not change (0.5.0 spec §4.4): tracing, gc hooks and tuning, trace/profile hooks, tool ids.

    Limit: ``sys.gettrace()``/``sys.getprofile()`` are per thread, so a hook set in a threadpool worker is not seen
    here; the static call-site rule (``test_interpreter_state_call_sites_only_in_session_modules``) covers ``src/``.
    """
    return {
        "tracemalloc tracing": tracemalloc.is_tracing(),
        "gc.callbacks": tuple(gc.callbacks),
        "gc enabled": gc.isenabled(),
        "gc threshold": gc.get_threshold(),
        "sys.settrace": sys.gettrace(),
        "sys.setprofile": sys.getprofile(),
        "sys.monitoring tool ids": tuple(sys.monitoring.get_tool(i) for i in range(6)),
    }


# spec §14: config's lazy getenv scan on its first GET is the one module allowed to read app source on a read
SOURCE_READ_EXEMPT = ("sharpit.engine.collectors.config",)
# every way a reader opens a file by name: open(), io.open (pathlib), tokenize.open's own reference to open
_OPENERS: tuple[tuple[Any, str], ...] = ((builtins, "open"), (io, "open"), (tokenize, "_builtin_open"))


def _exempt_caller() -> bool:
    frame = sys._getframe(2)  # noqa: SLF001 - the spy's caller and up
    while frame is not None:
        name = str(frame.f_globals.get("__name__", ""))
        if any(name == e or name.startswith(e + ".") for e in SOURCE_READ_EXEMPT):
            return True
        frame = frame.f_back
    return False


def _under(path: str, roots: list[str]) -> bool:
    for root in roots:
        try:
            if os.path.commonpath([path, root]) == root:
                return True
        except ValueError:  # another drive
            continue
    return False


class SideEffectGuard:
    """Blocks network access immediately; verify() reports filesystem, logger-level, environ and interpreter-state
    changes, and reads of watched app source (``watch_sources``)."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.violations: list[str] = []
        self._originals: list[tuple[Any, str, Any]] = []
        self.cwd = Path.cwd()  # the test's cwd at setup; a later chdir does not move the snapshot
        self._source_roots: list[str] = []
        self._spies: list[tuple[Any, str, Any]] = []
        self.source_reads: list[str] = []
        self.rebaseline()

    def rebaseline(self) -> None:
        self.violations.clear()
        self._cwd_snap = _snapshot(self.cwd)
        self._state_snap = _snapshot(self.state_dir)
        self._levels = _levels()
        self._environ = _environ()
        self._interpreter = _interpreter_state()
        self.source_reads.clear()

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

    def watch_sources(self, root: Path) -> None:
        """Report every file opened under ``root`` (the app's source tree) until ``unwatch_sources``."""
        self._source_roots.append(os.path.realpath(root))
        # list() copies the keys in one step: other threads (FastAPI on a TestClient portal) write linecache meanwhile
        for name in [n for n in list(linecache.cache) if _under(os.path.realpath(n), self._source_roots)]:
            del linecache.cache[name]  # a warm cache (FastAPI reads a host endpoint's source) would hide a later read
        if self._spies:
            return
        for owner, attr in _OPENERS:
            original = getattr(owner, attr)
            self._spies.append((owner, attr, original))
            setattr(owner, attr, self._open_spy(original))

    def _open_spy(self, original: Callable[..., Any]) -> Callable[..., Any]:
        def spy(file: Any, *args: Any, **kwargs: Any) -> Any:
            if isinstance(file, str | bytes | os.PathLike):
                path = os.path.realpath(os.fsdecode(file))  # pyright: ignore[reportUnknownArgumentType]
                if _under(path, self._source_roots) and not _exempt_caller():
                    self.source_reads.append(path)
            return original(file, *args, **kwargs)

        return spy

    def unwatch_sources(self) -> None:
        for owner, attr, original in reversed(self._spies):
            setattr(owner, attr, original)
        self._spies.clear()

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
        now_state = _interpreter_state()
        problems.extend(f"interpreter state changed: {k}" for k, v in now_state.items() if v != self._interpreter[k])
        problems.extend(f"app source read: {path}" for path in self.source_reads)
        assert not problems, "side effects detected: " + "; ".join(problems)


@pytest.fixture(autouse=True)
def _no_sqlite3_patch_leak(request: pytest.FixtureRequest) -> Iterator[None]:
    """sqlite3 source tests detach what they attach: a leak fails them. Elsewhere install() without a lifespan leaks.

    shortcut: 230+ tests install an app and never run its shutdown (a supported use), so the leak is only asserted
    for the files that exercise the source itself; upgrade if those tests get a shared fixture that uninstalls.
    """
    sqlite.detach_all()
    sqla.detach_all()  # install() without shutdown leaves contexts; 2+ make routing outside a request ambiguous
    # Transactions route through their own table: a leaked context (some with a fake engine registry) broke routing.
    with transactions._contexts_lock:  # pyright: ignore[reportPrivateUsage]
        transactions._contexts.clear()  # pyright: ignore[reportPrivateUsage]
        transactions._context_attachments.clear()  # pyright: ignore[reportPrivateUsage]
    yield
    leaked = sqlite.is_attached()
    sqlite.detach_all()
    strict = any(word in request.node.path.name for word in ("sqlite", "dispatch", "sources"))
    assert not (leaked and strict), (
        "the test left sqlite3.connect patched; detach it (uninstall_capture / sqlite.detach)"
    )


@pytest.fixture
def tmp_state_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    state_dir = tmp_path_factory.mktemp("sharpit-state")
    load_key(state_dir, create=True)  # so install() finds it and writes nothing, under the strict no_side_effects
    return state_dir


@pytest.fixture
def no_side_effects(tmp_state_dir: Path) -> Iterator[SideEffectGuard]:
    guard = SideEffectGuard(tmp_state_dir)
    guard.block_network()
    try:
        yield guard
    finally:
        guard.unblock_network()
        guard.unwatch_sources()
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


# Logging isolation for tests that run pytest in-process (``pytester.runpytest``). They share ``logging`` with every
# later test on the worker: a conftest calling ``basicConfig(level=INFO)`` once left root at INFO, so httpx's request
# lines landed in the log-tail tests. The guard fails the leaking test itself; ``restore_logging`` undoes a reconfigure.
# (Lives here, not in tests/pytest_plugin/: a second ``conftest`` module name collides without ``__init__.py``.)
_LOGGING_GUARDED = {"pytest_plugin", "testsession"}


def _logging_snapshot() -> dict[str, tuple[bool, int, bool, tuple[logging.Handler, ...]]]:
    loggers = [logging.root, *(lg for lg in logging.root.manager.loggerDict.values() if isinstance(lg, logging.Logger))]
    return {lg.name: (lg.disabled, lg.level, lg.propagate, tuple(lg.handlers)) for lg in loggers}


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """Put every logger back as it was, for a test whose in-process run reconfigures logging."""
    saved = _logging_snapshot()
    yield
    for name, (disabled, level, propagate, handlers) in saved.items():
        lg = logging.getLogger(None if name == "root" else name)
        lg.disabled, lg.level, lg.propagate = disabled, level, propagate
        lg.handlers[:] = handlers


@pytest.fixture(autouse=True)
def _logging_unchanged(request: pytest.FixtureRequest) -> Iterator[None]:
    if not _LOGGING_GUARDED.intersection(request.path.parts):
        yield
        return
    before = _logging_snapshot()
    yield
    after = _logging_snapshot()
    changed = sorted(name for name in before if after.get(name) != before[name])
    assert changed == [], "test leaked logging state (use the restore_logging fixture)"
