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
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
ENGINE = SRC / "sharpit" / "engine"
COLLECTORS = ENGINE / "collectors"
FRAMEWORKS = ("fastapi", "starlette")
ADAPTERS = ("sharpit.fastapi", "sharpit.pytest_plugin", "sharpit.ui")
GATEKEEPERS: dict[str, set[str]] = {
    "sqlalchemy": {"sharpit/engine/sqla"},  # a package: every module under engine/sqla/ (0.5.0 spec §4.1)
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
_MONITORING = (
    "use_tool_id",
    "free_tool_id",
    "clear_tool_id",
    "register_callback",
    "set_events",
    "set_local_events",
    "restart_events",
)
_PROCESS_STATE_PREFIXES = ("os.spawn", "os.exec")
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
        "sys.addaudithook",
        "os.system",
        "threading.settrace",
        "threading.setprofile",
        "threading.settrace_all_threads",
        "threading.setprofile_all_threads",
        *(f"sys.monitoring.{m}" for m in _MONITORING),
    }
)
RUNTIME_STATE_MODULES = {
    "sharpit/engine/sensors",
    "sharpit/pytest_plugin/swallowed.py",
}  # swallowed.py moves behind engine/sensors in lane S1
SESSION_MODULES = {"sharpit/pytest_plugin", "sharpit/engine/testsession"}
_STRICT_RUNTIME_STATE_CALLS = frozenset(
    {
        "sys.addaudithook",
        "sys.monitoring",
        *(f"sys.monitoring.{name}" for name in _MONITORING),
        "os.system",
    }
)


def _rel(path: Path) -> str:
    return path.relative_to(SRC).as_posix()


def _module_name(path: Path) -> str:
    parts = path.relative_to(SRC).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _within(name: str, packages: tuple[str, ...]) -> bool:
    return any(name == p or name.startswith(f"{p}.") for p in packages)


def _names_a_module(source: str, name: str) -> bool:
    """Whether ``from source import name`` imports a module. A ``sharpit`` name is one only when a file or package of
    that name exists under ``SRC``. A library's is read as one when ``source`` is its top level (``from urllib import
    request``); deeper, ``from sqlalchemy.engine import Engine`` names a class, and the source already matched."""
    if name == "*":
        return False
    if source.split(".")[0] != "sharpit":
        return "." not in source
    parent = SRC.joinpath(*source.split("."))
    # names, not ``is_file``: a case-insensitive disk would read ``Dialect`` as the module ``dialect.py``
    return parent.is_dir() and {name, f"{name}.py"} & {entry.name for entry in parent.iterdir()} != set()


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
                source = f"{base}.{node.module}" if node.module else base
            else:
                source = node.module or ""
            if source:
                yield source
                # ``from X import a`` reaches ``X.a`` when ``a`` is a module: a name re-exported by ``X`` is not one
                yield from (f"{source}.{a.name}" for a in node.names if _names_a_module(source, a.name))
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
    found: dict[
        tuple[str, str], str
    ] = {}  # one report per file and library: ``from sqlalchemy import event`` is two names
    for path in sorted((root or SRC / "sharpit").rglob("*.py")):
        for name in imports(path):
            for lib, allowed in GATEKEEPERS.items():
                if _within(name, (lib,)) and not _gatekeeper_allows(_rel(path), allowed):
                    found.setdefault(
                        (_rel(path), lib),
                        f"{_rel(path)} imports {name}: only {sorted(allowed) or 'no file'} may import {lib}",
                    )
    return list(found.values())


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
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
    ):
        base = _dotted(node.args[0], aliases)
        attr = node.args[1]
        suffix = ".".join(reversed(parts))
        return (
            ".".join(filter(None, (base, attr.value, suffix)))
            if base and isinstance(attr, ast.Constant) and isinstance(attr.value, str)
            else None
        )
    if not isinstance(node, ast.Name):
        return None
    chain = [node.id, *reversed(parts)]
    for index, part in enumerate(chain):
        if part in aliases:
            prefix = [] if index and chain[0] == "self" else chain[:index]
            return ".".join([*prefix, aliases[part], *chain[index + 1 :]])
    return ".".join(chain)


def _getattr_state_change(node: ast.Call, aliases: dict[str, str]) -> str | None:
    if not isinstance(node.func, ast.Name) or node.func.id != "getattr" or len(node.args) < 2:
        return None
    if not isinstance(node.args[1], ast.Constant) or not isinstance(node.args[1].value, str):
        return None
    if node.args[1].value in _MONITORING:
        return f"sys.monitoring.{node.args[1].value}"
    if node.args[1].value in ("monitoring", "addaudithook"):
        return f"sys.{node.args[1].value}"
    name = ".".join(filter(None, (_dotted(node.args[0], aliases), node.args[1].value)))
    return name if name in INTERPRETER_STATE_CALLS or name == "sys.monitoring" else None


def _state_target_changes(node: ast.AST, aliases: dict[str, str]) -> Iterator[tuple[int, str]]:
    targets = (
        list(node.targets)
        if isinstance(node, ast.Assign | ast.Delete)
        else [node.target]
        if isinstance(node, ast.AugAssign)
        else []
    )
    for target in targets:
        dotted = _dotted(target.value if isinstance(target, ast.Subscript) else target, aliases)
        if dotted in INTERPRETER_STATE_CALLS or (dotted and dotted.startswith(_PROCESS_STATE_PREFIXES)):
            yield node.lineno, dotted


def _state_changes(tree: ast.Module) -> Iterator[tuple[int, str]]:
    aliases = _aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _getattr_state_change(node, aliases) or _dotted(node.func, aliases)
            fetches_monitoring = name == "sys.monitoring"  # getattr(x, "monitoring") hands out the namespace
            if (
                fetches_monitoring
                or name in INTERPRETER_STATE_CALLS
                or (name and name.startswith(_PROCESS_STATE_PREFIXES))
            ):
                yield node.lineno, name
        elif isinstance(node, ast.Attribute) and node.attr in (*_MONITORING, "addaudithook"):
            name = _dotted(node, aliases)
            yield (
                node.lineno,
                name
                if name in INTERPRETER_STATE_CALLS
                else ("sys.addaudithook" if node.attr == "addaudithook" else f"sys.monitoring.{node.attr}"),
            )
        else:
            yield from _state_target_changes(node, aliases)


def interpreter_state_violations(root: Path | None = None) -> list[str]:
    """Report state changes outside their session or runtime-state package allow-lists."""
    found: list[str] = []
    for path in sorted((root or SRC / "sharpit").rglob("*.py")):
        rel = _rel(path)
        for line, name in sorted(set(_state_changes(ast.parse(path.read_text(encoding="utf-8"))))):
            allowed = (
                RUNTIME_STATE_MODULES
                if name in _STRICT_RUNTIME_STATE_CALLS or name.startswith(_PROCESS_STATE_PREFIXES)
                else SESSION_MODULES
            )
            if not _gatekeeper_allows(rel, allowed):
                found.append(f"{rel}:{line} calls {name}")
    return found


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
    (engine / "sqla").mkdir()
    plant("sqla/listeners.py", "import sqlalchemy.pool\n")

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


@pytest.mark.parametrize(
    "source, expected",
    [
        ("import sys\nsys.addaudithook(print)\n", "sys.addaudithook"),
        ('import sys\nsys.monitoring.use_tool_id(1, "x")\n', "sys.monitoring.use_tool_id"),
        ("import sys\nsys.monitoring.set_events(1, 0)\n", "sys.monitoring.set_events"),
        ('import sys\nsys.monitoring.register_callback(1, "LINE", None)\n', "sys.monitoring.register_callback"),
        ("import sys\nsys.monitoring.free_tool_id(1)\n", "sys.monitoring.free_tool_id"),
        ("import sys\nsys.monitoring.restart_events()\n", "sys.monitoring.restart_events"),
        ("import sys\nsys.monitoring.set_local_events(1, object, 0)\n", "sys.monitoring.set_local_events"),
        ('import sys\ngetattr(sys, "addaudithook")(print)\n', "sys.addaudithook"),
        ('import sys\ngetattr(sys.monitoring, "set_events")(1, 0)\n', "sys.monitoring.set_events"),
        ('import os\nos.system("true")\n', "os.system"),
        ('import os\nos.spawnv(0, "x", [])\n', "os.spawnv"),
        ('import os\nos.execv("x", [])\n', "os.execv"),
    ],
)
def test_runtime_state_calls_outside_sensors_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, expected: str
) -> None:
    monkeypatch.setitem(globals(), "SRC", tmp_path / "src")
    engine = tmp_path / "src" / "sharpit" / "engine"
    (engine / "rogue.py").parent.mkdir(parents=True)
    (engine / "rogue.py").write_text(source, encoding="utf-8")

    violations = interpreter_state_violations()

    assert any("rogue.py" in violation and expected in violation for violation in violations)


def test_runtime_state_calls_inside_sensors_are_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(globals(), "SRC", tmp_path / "src")
    sensors = tmp_path / "src" / "sharpit" / "engine" / "sensors"
    sensors.mkdir(parents=True)
    (sensors / "audit.py").write_text("import sys\nsys.addaudithook(print)\n", encoding="utf-8")

    assert interpreter_state_violations() == []


def test_only_swallowed_plugin_module_keeps_its_runtime_state_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(globals(), "SRC", tmp_path / "src")
    plugin = tmp_path / "src" / "sharpit" / "pytest_plugin"
    plugin.mkdir(parents=True)
    (plugin / "swallowed.py").write_text("import sys\nsys.monitoring.use_tool_id(3, 'sharpit')\n", encoding="utf-8")
    (plugin / "other.py").write_text("import sys\nsys.addaudithook(print)\n", encoding="utf-8")

    assert interpreter_state_violations() == ["sharpit/pytest_plugin/other.py:2 calls sys.addaudithook"]


@pytest.mark.parametrize(
    "source",
    [
        "import sys\nclass Holder:\n    monitoring = sys.monitoring\n"
        "    def change(self):\n        self.monitoring.set_events(1, 0)\n",
        'import sys\nm = getattr(sys, "monitoring")\nm.set_events(1, 0)\n',
        'import sys\ngetattr(sys, "monitoring").set_events(1, 0)\n',
    ],
)
def test_runtime_state_attribute_shapes_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    monkeypatch.setitem(globals(), "SRC", tmp_path / "src")
    rogue = tmp_path / "src" / "sharpit" / "engine" / "rogue.py"
    rogue.parent.mkdir(parents=True)
    rogue.write_text(source, encoding="utf-8")

    assert any("rogue.py" in item and "sys.monitoring.set_events" in item for item in interpreter_state_violations())


@pytest.mark.parametrize("name", ["monitoring", "addaudithook"])
def test_runtime_state_getattr_names_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setitem(globals(), "SRC", tmp_path / "src")
    rogue = tmp_path / "src" / "sharpit" / "engine" / "rogue.py"
    rogue.parent.mkdir(parents=True)
    rogue.write_text(f"value = getattr(holder, {name!r})\n", encoding="utf-8")

    assert any(f"calls sys.{name}" in item for item in interpreter_state_violations())


def test_strict_runtime_calls_are_rejected_outside_sensors_and_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(globals(), "SRC", tmp_path / "src")
    for rel in ("sharpit/pytest_plugin/other.py", "sharpit/engine/testsession/other.py"):
        path = tmp_path / "src" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("import sys\nsys.monitoring.use_tool_id(1, 'x')\n", encoding="utf-8")

    assert len(interpreter_state_violations()) == 2


def test_side_effect_guard_blocks_audit_hook_install(no_side_effects) -> None:
    source = Path(__file__).resolve().parents[2] / "src" / "sharpit" / "probe.py"
    with pytest.raises(TypeError):  # the spy calls the original: a bad call installs nothing that outlives the test
        exec(compile("import sys\nsys.addaudithook()", str(source), "exec"))
    with pytest.raises(AssertionError, match="sys.addaudithook"):
        no_side_effects.verify()
    no_side_effects.rebaseline()


def test_side_effect_guard_blocks_monitoring_event_set(no_side_effects) -> None:
    import sys

    monitoring = sys.monitoring
    tool = next(tool for tool in range(6) if monitoring.get_tool(tool) is None)
    monitoring.use_tool_id(tool, "sharpit-test")
    try:
        source = Path(__file__).resolve().parents[2] / "src" / "sharpit" / "probe.py"
        exec(compile(f"import sys\nsys.monitoring.set_events({tool}, 0)", str(source), "exec"))
    finally:
        monitoring.free_tool_id(tool)
    with pytest.raises(AssertionError, match="sys.monitoring.set_events"):
        no_side_effects.verify()
    no_side_effects.rebaseline()


@pytest.mark.parametrize("method, arguments", [("register_callback", "1, 'LINE', None"), ("restart_events", "1")])
def test_side_effect_guard_records_additional_monitoring_calls_after_network_unblock(
    no_side_effects, method: str, arguments: str
) -> None:
    no_side_effects.unblock_network()
    source = Path(__file__).resolve().parents[2] / "src" / "sharpit" / "probe.py"
    with pytest.raises(TypeError):  # the spy calls the original: bad arguments change nothing
        exec(compile(f"import sys\nsys.monitoring.{method}({arguments})", str(source), "exec"))

    with pytest.raises(AssertionError, match=f"sys.monitoring.{method}"):
        no_side_effects.verify()
    no_side_effects.rebaseline()


def test_sysmon_coverage_child_does_not_crash(no_side_effects) -> None:
    """The subprocess test below runs this fixture while coverage owns a sys.monitoring tool id."""


def test_side_effect_guard_is_compatible_with_sysmon_coverage(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["COVERAGE_CORE"] = "sysmon"
    env["COVERAGE_FILE"] = str(tmp_path / ".coverage")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-n",
            "2",
            "--cov=src/sharpit",
            "tests/engine/test_import_boundary.py::test_sysmon_coverage_child_does_not_crash",
        ],
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr


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


# 0.5.0 SQL output architecture, section 10 step 3: the ``sqltext`` package and its boundary.
SQLTEXT = "sharpit.engine.sqltext"
SQLTEXT_ADAPTERS = (
    "sharpit.engine.sqla",
    "sharpit.engine.otel",
    "sharpit.engine.sources",
    "sharpit.engine.capture",
    "sharpit.engine.context",
)


def _sqltext_files(root: Path | None = None) -> list[Path]:
    return sorted(((root or SRC / "sharpit") / "engine" / "sqltext").rglob("*.py"))


def sqltext_internal_violations(root: Path | None = None) -> list[str]:
    inside = {_rel(p) for p in _sqltext_files(root)}
    return [
        f"{_rel(path)} imports {name}"
        for path in sorted((root or SRC / "sharpit").rglob("*.py"))
        if _rel(path) not in inside
        for name in imports(path)
        if name.startswith(f"{SQLTEXT}.")
    ]


def sqltext_adapter_violations(root: Path | None = None) -> list[str]:
    return [
        f"{_rel(path)} imports {name}"
        for path in _sqltext_files(root)
        for name in imports(path)
        if _within(name, (*ADAPTERS, *SQLTEXT_ADAPTERS))
    ]


def sqltext_masking_violations(root: Path | None = None) -> list[str]:
    return [
        f"{_rel(path)} imports {name}"
        for path in _sqltext_files(root)
        if path.stem in ("family", "lexer", "render")
        for name in imports(path)
        if _within(name, ("sharpit.engine.masking",))
    ]


def sqltext_errors_private_violations(root: Path | None = None) -> list[str]:
    errors = (root or SRC / "sharpit") / "engine" / "sqltext" / "errors.py"
    if not errors.exists():
        return []
    tree = ast.parse(errors.read_text(encoding="utf-8"))
    return [
        f"{_rel(errors)} imports private lexer name {alias.name}"
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("sqltext.lexer")
        for alias in node.names
        if alias.name.startswith("_")
    ]


def _plant_sqltext(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, str]) -> Path:
    monkeypatch.setitem(globals(), "SRC", tmp_path / "src")
    root = tmp_path / "src" / "sharpit"
    for rel, code in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(code, encoding="utf-8")
    return root


def test_sqltext_internals_stay_inside() -> None:
    assert sqltext_internal_violations() == []


def test_planted_sqltext_internal_import_outside_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _plant_sqltext(
        tmp_path,
        monkeypatch,
        {
            "engine/sqltext/__init__.py": "from sharpit.engine.sqltext.dialect import Dialect\n",
            "engine/sqltext/dialect.py": "",
            "engine/masking.py": "from sharpit.engine.sqltext import MASK\n",
            "engine/tools.py": "from sharpit.engine.sqltext.lexer import t\nfrom sharpit.engine.sqltext import D\n",
        },
    )

    assert sqltext_internal_violations(root) == ["sharpit/engine/tools.py imports sharpit.engine.sqltext.lexer"]


def test_sqltext_imports_no_adapter() -> None:
    assert sqltext_adapter_violations() == []


def test_planted_sqltext_adapter_import_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _plant_sqltext(
        tmp_path,
        monkeypatch,
        {
            "engine/sqltext/dialect.py": "from sharpit.engine.sqla import x\n",
            "engine/sqltext/family.py": "from sharpit.fastapi import x\n",
            "engine/sqltext/lexer.py": "from sharpit.engine.capture.statement import y\nimport re\n",
            "engine/sqltext/render.py": "from sharpit.fastapi import z\n",
            "engine/sqltext/constants.py": "from sharpit.engine.sqltext.dialect import Dialect\n",
        },
    )

    assert sqltext_adapter_violations(root) == [
        "sharpit/engine/sqltext/dialect.py imports sharpit.engine.sqla",
        "sharpit/engine/sqltext/family.py imports sharpit.fastapi",
        "sharpit/engine/sqltext/lexer.py imports sharpit.engine.capture.statement",
        "sharpit/engine/sqltext/render.py imports sharpit.fastapi",
    ]


def test_sqltext_readers_and_render_import_no_masking() -> None:
    assert sqltext_masking_violations() == []


def test_planted_masking_import_in_lexer_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _plant_sqltext(
        tmp_path,
        monkeypatch,
        {
            "engine/sqltext/lexer.py": "from sharpit.engine.masking import mask\n",
            "engine/sqltext/family.py": "from sharpit.engine.masking import mask\n",
            "engine/sqltext/render.py": "import sharpit.engine.masking\n",
            "engine/sqltext/dialect.py": "from sharpit.engine.masking import mask\n",
        },
    )

    assert sqltext_masking_violations(root) == [
        "sharpit/engine/sqltext/family.py imports sharpit.engine.masking",
        "sharpit/engine/sqltext/lexer.py imports sharpit.engine.masking",
        "sharpit/engine/sqltext/render.py imports sharpit.engine.masking",
    ]


def test_sqltext_names_no_optional_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = gatekeeper_violations()
    root = _plant_sqltext(tmp_path, monkeypatch, {"engine/sqltext/errors.py": "import sqlalchemy\n"})

    planted = gatekeeper_violations(root)

    assert [v for v in real if "engine/sqltext/" in v] == []
    assert planted == [
        "sharpit/engine/sqltext/errors.py imports sqlalchemy: only ['sharpit/engine/sqla'] may import sqlalchemy"
    ]


def test_errors_imports_no_lexer_private() -> None:
    assert sqltext_errors_private_violations() == []


def test_a_planted_error_import_of_a_lexer_private_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _plant_sqltext(
        tmp_path,
        monkeypatch,
        {"engine/sqltext/errors.py": "from sharpit.engine.sqltext.lexer import _scan\n"},
    )

    assert sqltext_errors_private_violations(root) == [
        "sharpit/engine/sqltext/errors.py imports private lexer name _scan"
    ]


# A ``from X import a`` form names ``X.a`` when ``a`` is a submodule: every rule has to see it (review of Tasks 9, 10).
FROM_FORM_PLANTS: dict[str, tuple[dict[str, str], Callable[[Path], list[str]], list[str]]] = {
    "sqltext_submodule_from_outside": (
        {"engine/sqltext/lexer.py": "", "engine/tools.py": "from sharpit.engine.sqltext import lexer\n"},
        sqltext_internal_violations,
        ["sharpit/engine/tools.py imports sharpit.engine.sqltext.lexer"],
    ),
    "sqltext_submodule_relative_from_outside": (
        {"engine/sqltext/lexer.py": "", "engine/tools.py": "from .sqltext import lexer\n"},
        sqltext_internal_violations,
        ["sharpit/engine/tools.py imports sharpit.engine.sqltext.lexer"],
    ),
    "sqltext_root_name_is_not_a_submodule": (
        {"engine/sqltext/__init__.py": "", "engine/tools.py": "from sharpit.engine.sqltext import Dialect, MASK\n"},
        sqltext_internal_violations,
        [],
    ),
    "sqla_and_otel_in_sqltext": (
        {
            "engine/sqla/__init__.py": "",
            "engine/otel.py": "",
            "engine/sqltext/dialect.py": "from sharpit.engine import sqla\nfrom sharpit.engine import otel\n",
        },
        sqltext_adapter_violations,
        [
            "sharpit/engine/sqltext/dialect.py imports sharpit.engine.sqla",
            "sharpit/engine/sqltext/dialect.py imports sharpit.engine.otel",
        ],
    ),
    "adapter_package_from_sharpit": (
        {"fastapi/__init__.py": "", "engine/tools.py": "from sharpit import fastapi\n"},
        lambda root: adapter_violations(root / "engine"),
        ["sharpit/engine/tools.py imports sharpit.fastapi"],
    ),
    "masking_in_lexer_from_engine": (
        {"engine/masking.py": "", "engine/sqltext/lexer.py": "from sharpit.engine import masking\n"},
        sqltext_masking_violations,
        ["sharpit/engine/sqltext/lexer.py imports sharpit.engine.masking"],
    ),
    "masking_in_render_relative_parent": (
        {"engine/masking.py": "", "engine/sqltext/render.py": "from .. import masking\n"},
        sqltext_masking_violations,
        ["sharpit/engine/sqltext/render.py imports sharpit.engine.masking"],
    ),
    "collector_reaches_a_sibling": (
        {
            "engine/collectors/mappings.py": "",
            "engine/collectors/beans.py": "from sharpit.engine.collectors import mappings\n",
        },
        lambda root: collector_violations(root / "engine" / "collectors"),
        [
            "sharpit/engine/collectors/beans.py imports sharpit.engine.collectors.mappings:"
            " collector 'beans' reaches into 'mappings'"
        ],
    ),
    "collector_reaches_a_sibling_relative": (
        {"engine/collectors/mappings.py": "", "engine/collectors/beans.py": "from . import mappings\n"},
        lambda root: collector_violations(root / "engine" / "collectors"),
        [
            "sharpit/engine/collectors/beans.py imports sharpit.engine.collectors.mappings:"
            " collector 'beans' reaches into 'mappings'"
        ],
    ),
    "network_client_from_urllib": (
        {"engine/tools.py": "from urllib import request\n"},
        lambda root: [v.split(": only")[0] for v in gatekeeper_violations(root)],
        ["sharpit/engine/tools.py imports urllib.request"],
    ),
}


@pytest.mark.parametrize("plant", FROM_FORM_PLANTS)
def test_a_from_import_of_a_submodule_is_seen(plant: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files, check, wanted = FROM_FORM_PLANTS[plant]
    root = _plant_sqltext(tmp_path, monkeypatch, files)

    assert check(root) == wanted
