"""Module boundaries, checked on every run (Spring Modulith style). AGENTS.md "Architecture rules" lists the same rules.

1. The engine is framework-free: no FastAPI or Starlette import (a ``TYPE_CHECKING`` block is allowed).
2. The engine never imports an adapter (``sharpit.fastapi``, ``sharpit.ui``): adapters depend on the engine only.
3. Each collector under ``engine/collectors/`` is a module of its own and never imports another collector. Shared
   code goes in the engine (``context``, ``paging``, ``spi``, ...), not in a sibling collector.
4. Gatekeepers: an optional dependency or a network client is imported by one named file only, so the rest of the
   package works without it (CI's ``no-sqlalchemy`` job) and nothing else can reach the network (safety model).
"""

from __future__ import annotations

import ast
import functools
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
    "urllib.request": {"sharpit/engine/collectors/vulns/osv.py", "sharpit/engine/collectors/vulns/epss.py"},
    "http.client": {"sharpit/engine/collectors/vulns/osv.py"},
    "socket": set(),
    "ssl": set(),
    "pytest": {"sharpit/pytest_plugin/__init__.py", "sharpit/pytest_plugin/marker.py"},
    "_pytest": {"sharpit/pytest_plugin/__init__.py", "sharpit/pytest_plugin/marker.py"},
}


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


def gatekeeper_violations(root: Path | None = None) -> list[str]:
    return [
        f"{_rel(path)} imports {name}: only {sorted(allowed) or 'no file'} may import {lib}"
        for path in sorted((root or SRC / "sharpit").rglob("*.py"))
        for name in imports(path)
        for lib, allowed in GATEKEEPERS.items()
        if _within(name, (lib,)) and _rel(path) not in allowed
    ]


def test_engine_modules_do_not_import_fastapi_or_starlette():
    assert framework_violations() == []


def test_engine_never_imports_an_adapter():
    assert adapter_violations() == []


def test_collectors_never_import_each_other():
    assert collector_violations() == []


def test_optional_and_network_libraries_stay_behind_their_gatekeeper():
    assert gatekeeper_violations() == []


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
