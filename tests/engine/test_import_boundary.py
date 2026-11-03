"""Module boundaries, checked on every run (Spring Modulith style). AGENTS.md "Architecture rules" lists the same rules.

1. The engine is framework-free: no FastAPI or Starlette import (a ``TYPE_CHECKING`` block is allowed).
2. The engine never imports an adapter (``sharpit.fastapi``, ``sharpit.ui``): adapters depend on the engine only.
3. Each collector under ``engine/collectors/`` is a module of its own and never imports another collector. Shared
   code goes in the engine (``context``, ``paging``, ``spi``, ...), not in a sibling collector.
4. Gatekeepers: an optional dependency or a network client is imported by one named file only, so the rest of the
   package works without it (CI's ``no-sqlalchemy`` job) and nothing else can reach the network (safety model).
5. Interpreter state (0.5.0 spec §4.4, §9): calls that change it (``tracemalloc.start``, ``gc.callbacks`` mutation,
   ``sys.settrace``/``setprofile``, ``sys.monitoring.use_tool_id``, ...) only in the test-session modules. Call
   sites, not imports: a ``gc.get_objects()`` heap walk stays legal anywhere.
"""

from __future__ import annotations

import ast
import functools
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
ENGINE = SRC / "sharpit" / "engine"
COLLECTORS = ENGINE / "collectors"
FRAMEWORKS = ("fastapi", "starlette")
ADAPTERS = ("sharpit.fastapi", "sharpit.pytest_plugin", "sharpit.ui")
GATEKEEPERS: dict[str, set[str]] = {
    "sqlalchemy": {"sharpit/engine/sqla.py"},
    "sqlite3": {"sharpit/engine/sources/sqlite.py"},
    "alembic": set(),
    "pydantic_settings": {"sharpit/engine/collectors/config/settings_source.py"},
    "opentelemetry": {"sharpit/engine/otel.py"},
    "urllib.request": {"sharpit/engine/collectors/vulns/osv.py", "sharpit/engine/collectors/vulns/epss.py"},
    "http.client": {"sharpit/engine/collectors/vulns/osv.py"},
    "socket": set(),
    "ssl": set(),
    "pytest": {"sharpit/pytest_plugin"},
    "_pytest": {"sharpit/pytest_plugin"},
}


# a dotted call (or assignment target) that changes interpreter state; reads such as gc.get_objects() are not here
_GC_CALLBACKS = ("append", "extend", "insert", "remove", "pop", "clear", "__setitem__", "__delitem__", "__iadd__")
_MONITORING = ("use_tool_id", "free_tool_id", "clear_tool_id", "register_callback", "set_events", "set_local_events")
INTERPRETER_STATE_CALLS: frozenset[str] = frozenset(
    {
        "tracemalloc.start",
        "tracemalloc.stop",
        "tracemalloc.clear_traces",
        "gc.callbacks",
        *(f"gc.callbacks.{m}" for m in _GC_CALLBACKS),
        "gc.set_threshold",
        "gc.disable",
        "gc.enable",
        "gc.freeze",
        "gc.unfreeze",
        "gc.set_debug",
        "sys.settrace",
        "sys.setprofile",
        "threading.settrace",
        "threading.setprofile",
        "threading.settrace_all_threads",
        "threading.setprofile_all_threads",
        *(f"sys.monitoring.{m}" for m in _MONITORING),
    }
)
SESSION_MODULES = {"sharpit/pytest_plugin", "sharpit/engine/testsession"}


def _rel(path: Path) -> str:
    return path.relative_to(SRC).as_posix()


def _module_name(path: Path) -> str:
    parts = path.relative_to(SRC).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _within(name: str, packages: tuple[str, ...]) -> bool:
    return any(name == p or name.startswith(f"{p}.") for p in packages)


def imports(path: Path, *, skip_type_checking: bool = False) -> tuple[str, ...]:
    """Absolute names of the modules ``path`` imports, relative imports resolved. Each file is parsed once per run."""
    return _imports(path, path.stat().st_mtime_ns, skip_type_checking=skip_type_checking)


@functools.cache
def _imports(path: Path, _mtime_ns: int, *, skip_type_checking: bool) -> tuple[str, ...]:
    module = _module_name(path)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]

    def visit(node: ast.AST) -> Iterator[str]:
        if skip_type_checking and isinstance(node, ast.If) and getattr(node.test, "id", None) == "TYPE_CHECKING":
            for child in node.orelse:
                yield from visit(child)
            return
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                yield f"{base}.{node.module}" if node.module else base
            elif node.module:
                yield node.module
        for child in ast.iter_child_nodes(node):
            yield from visit(child)

    return tuple(visit(ast.parse(path.read_text(encoding="utf-8"))))


def _collector(module: str) -> str | None:
    parts = module.split(".")
    return parts[3] if parts[:3] == ["sharpit", "engine", "collectors"] and len(parts) > 3 else None


def framework_violations(root: Path = ENGINE) -> list[str]:
    return [
        f"{_rel(path)} imports {name}"
        for path in sorted(root.rglob("*.py"))
        for name in imports(path, skip_type_checking=True)
        if _within(name, FRAMEWORKS)
    ]


def adapter_violations(root: Path = ENGINE) -> list[str]:
    return [
        f"{_rel(path)} imports {name}"
        for path in sorted(root.rglob("*.py"))
        for name in imports(path)
        if _within(name, ADAPTERS)
    ]


def collector_violations(root: Path = COLLECTORS) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        own = _collector(_module_name(path))
        for name in imports(path):
            other = _collector(name)
            if own and other and other != own:
                found.append(f"{_rel(path)} imports {name}: collector {own!r} reaches into {other!r}")
    return found


def _gatekeeper_allows(rel: str, allowed: set[str]) -> bool:
    """A gatekeeper entry is a file, or a package directory that covers every module below it."""
    return rel in allowed or any(rel.startswith(f"{entry}/") for entry in allowed)


def gatekeeper_violations(root: Path | None = None) -> list[str]:
    return [
        f"{_rel(path)} imports {name}: only {sorted(allowed) or 'no file'} may import {lib}"
        for path in sorted((root or SRC / "sharpit").rglob("*.py"))
        for name in imports(path)
        for lib, allowed in GATEKEEPERS.items()
        if _within(name, (lib,)) and not _gatekeeper_allows(_rel(path), allowed)
    ]


def _aliases(tree: ast.Module) -> dict[str, str]:
    """Local name -> dotted name, from imports and plain ``name = a.b`` assignments anywhere in the module."""
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update({(a.asname or a.name.split(".")[0]): (a.name if a.asname else a.name.split(".")[0])
                          for a in node.names})  # fmt: skip
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.update({(a.asname or a.name): f"{node.module}.{a.name}" for a in node.names})
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            dotted = _dotted(node.value, found)
            if dotted is not None:
                found[node.targets[0].id] = dotted
    return found


def _dotted(node: ast.expr, aliases: dict[str, str]) -> str | None:
    """``a.b.c`` with ``a`` resolved through ``aliases`` (an unknown root stays as written), else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([aliases.get(node.id, node.id), *reversed(parts)])


def _state_changes(tree: ast.Module) -> Iterator[tuple[int, str]]:
    aliases = _aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            targets: list[ast.expr] = [node.func]
        elif isinstance(node, ast.Assign | ast.Delete):
            targets = list(node.targets)
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            base = target.value if isinstance(target, ast.Subscript) else target
            dotted = _dotted(base, aliases)
            if dotted in INTERPRETER_STATE_CALLS:
                yield node.lineno, dotted


def interpreter_state_violations(root: Path | None = None) -> list[str]:
    """``<file>:<line> calls <name>`` for each interpreter-state change outside the test-session modules."""
    return [
        f"{_rel(path)}:{line} calls {name}"
        for path in sorted((root or SRC / "sharpit").rglob("*.py"))
        if not _gatekeeper_allows(_rel(path), SESSION_MODULES)
        for line, name in sorted(_state_changes(ast.parse(path.read_text(encoding="utf-8"))))
    ]


def test_engine_modules_do_not_import_fastapi_or_starlette():
    assert framework_violations() == []


def test_engine_never_imports_an_adapter():
    assert adapter_violations() == []


def test_collectors_never_import_each_other():
    assert collector_violations() == []


def test_optional_and_network_libraries_stay_behind_their_gatekeeper():
    assert gatekeeper_violations() == []


def test_pytest_gatekeeper_covers_the_plugin_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # replaces test_pytest_gatekeeper_allows_every_plugin_submodule (its helpers changed after its red commit)
    source = tmp_path / "src"
    plugin = source / "sharpit" / "pytest_plugin"
    engine = source / "sharpit" / "engine"
    plugin.mkdir(parents=True)
    engine.mkdir(parents=True)
    (plugin / "session.py").write_text("import pytest\n", encoding="utf-8")
    (plugin / "apps.py").write_text("import _pytest\n", encoding="utf-8")
    (engine / "rogue.py").write_text("import pytest\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "SRC", source)

    violations = gatekeeper_violations()

    assert violations == ["sharpit/engine/rogue.py imports pytest: only ['sharpit/pytest_plugin'] may import pytest"]


def test_opentelemetry_import_is_confined_to_engine_otel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # replaces test_opentelemetry_stays_behind_engine_otel_gatekeeper (its helpers changed after its red commit)
    source = tmp_path / "src"
    engine = source / "sharpit" / "engine"
    engine.mkdir(parents=True)
    (engine / "otel.py").write_text("import opentelemetry.trace\n", encoding="utf-8")
    (engine / "tools.py").write_text("import opentelemetry.trace\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "SRC", source)

    violations = gatekeeper_violations()

    assert violations == [
        "sharpit/engine/tools.py imports opentelemetry.trace: only ['sharpit/engine/otel.py'] may import opentelemetry"
    ]


def test_the_rules_catch_a_violation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each rule fails on a planted import, so a green run means the boundaries hold, not that the scan saw nothing."""
    monkeypatch.setitem(globals(), "SRC", tmp_path / "src")
    engine = tmp_path / "src" / "sharpit" / "engine"
    (engine / "collectors" / "loggers").mkdir(parents=True)

    def plant(rel: str, code: str) -> None:
        (engine / rel).write_text(code, encoding="utf-8")

    plant("collectors/loggers/__init__.py", "from ..health import health_report\n")
    plant("collectors/beans.py", "from sharpit.engine.collectors.mappings import x\n")
    plant("tools.py", "import starlette.requests\nfrom sharpit.fastapi.adapter import y\nimport urllib.request\n")
    plant("sqla.py", "import sqlalchemy.pool\n")

    assert framework_violations(engine) == ["sharpit/engine/tools.py imports starlette.requests"]
    assert adapter_violations(engine) == ["sharpit/engine/tools.py imports sharpit.fastapi.adapter"]
    assert [v.split(": ")[1] for v in collector_violations(engine / "collectors")] == [
        "collector 'beans' reaches into 'mappings'",
        "collector 'loggers' reaches into 'health'",
    ]
    assert [v.split(":")[0] for v in gatekeeper_violations(engine)] == [
        "sharpit/engine/tools.py imports urllib.request"
    ]


STATE_PROBE = """import gc
import sys
import tracemalloc as tm
from sys import settrace
tm.start()
gc.callbacks.append(print)
gc.callbacks[:] = []
settrace(None)
mon = sys.monitoring
mon.use_tool_id(4, "x")
gc.get_objects()
gc.get_referrers(gc)
"""


def test_interpreter_state_call_sites_only_in_session_modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Planted state changes outside the session modules are reported; heap walks and session modules are not."""
    monkeypatch.setitem(globals(), "SRC", tmp_path / "src")
    engine = tmp_path / "src" / "sharpit" / "engine"
    plugin = tmp_path / "src" / "sharpit" / "pytest_plugin"
    for folder in (engine / "collectors", engine / "testsession", plugin):
        folder.mkdir(parents=True)
    (engine / "collectors" / "probe.py").write_text(STATE_PROBE, encoding="utf-8")
    (engine / "testsession" / "memory.py").write_text("import tracemalloc\ntracemalloc.start()\n", encoding="utf-8")
    (plugin / "swallowed.py").write_text("import sys\nsys.monitoring.use_tool_id(3, 'sharpit')\n", encoding="utf-8")

    planted = interpreter_state_violations()
    monkeypatch.undo()
    real = interpreter_state_violations()

    assert planted == [
        "sharpit/engine/collectors/probe.py:5 calls tracemalloc.start",
        "sharpit/engine/collectors/probe.py:6 calls gc.callbacks.append",
        "sharpit/engine/collectors/probe.py:7 calls gc.callbacks",
        "sharpit/engine/collectors/probe.py:8 calls sys.settrace",
        "sharpit/engine/collectors/probe.py:10 calls sys.monitoring.use_tool_id",
    ]
    assert real == []


def test_sqla_package_is_the_only_sqlalchemy_importer() -> None:
    """0.5.0 spec §4.1: every module that imports SQLAlchemy lives in the ``engine/sqla/`` package."""
    importers = [
        _rel(path)
        for path in sorted((SRC / "sharpit").rglob("*.py"))
        if any(_within(n, ("sqlalchemy",)) for n in imports(path))
    ]
    outside = [rel for rel in importers if not rel.startswith("sharpit/engine/sqla/")]

    assert importers, "no module imports sqlalchemy: the scan proves nothing"
    assert outside == []


def test_planted_sqlalchemy_import_outside_package_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The ``sqla/`` gatekeeper allows every module of the package and nothing beside it, ``sqla_extra.py`` included."""
    monkeypatch.setitem(globals(), "SRC", tmp_path / "src")
    engine = tmp_path / "src" / "sharpit" / "engine"
    (engine / "sqla").mkdir(parents=True)
    (engine / "sqla" / "__init__.py").write_text("import sqlalchemy\n", encoding="utf-8")
    (engine / "sqla" / "listeners.py").write_text("from sqlalchemy import event\n", encoding="utf-8")
    (engine / "sqla_extra.py").write_text("import sqlalchemy.orm\n", encoding="utf-8")
    (engine / "models.py").write_text("from sqlalchemy.engine import Engine\n", encoding="utf-8")

    violations = [v.split(":")[0] for v in gatekeeper_violations()]

    assert violations == [
        "sharpit/engine/models.py imports sqlalchemy.engine",
        "sharpit/engine/sqla_extra.py imports sqlalchemy.orm",
    ]
