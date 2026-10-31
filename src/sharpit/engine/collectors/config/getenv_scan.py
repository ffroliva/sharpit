"""Static AST scan for literal-key getenv calls. Never imports or executes scanned code."""

import ast
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_SKIP_DIRS = frozenset({".venv", "venv", "node_modules", "__pycache__", "site-packages"})
_MAX_BYTES = 1_000_000


@dataclass
class GetenvFinding:
    key: str
    default: str | None
    location: str


def _is_os_attr(node: ast.expr, attr: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == attr
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _literal_key(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _literal_default(call: ast.Call) -> str | None:
    # Non-literal defaults stay None: never evaluated.
    arg = call.args[1] if len(call.args) > 1 else next((k.value for k in call.keywords if k.arg == "default"), None)
    if isinstance(arg, ast.Constant) and arg.value is not None:
        return str(arg.value)
    return None


def _scan_source(source: str, location: str) -> list[GetenvFinding]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return []
    environ_names: set[str] = set()
    getenv_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "os" and node.level == 0:
            for alias in node.names:
                if alias.name == "environ":
                    environ_names.add(alias.asname or "environ")
                elif alias.name == "getenv":
                    getenv_names.add(alias.asname or "getenv")

    def is_environ(n: ast.expr) -> bool:
        return _is_os_attr(n, "environ") or (isinstance(n, ast.Name) and n.id in environ_names)

    found: list[GetenvFinding] = []
    for node in ast.walk(tree):
        key: str | None = None
        default: str | None = None
        line = 0
        if isinstance(node, ast.Call) and node.args:
            f = node.func
            if (
                _is_os_attr(f, "getenv")
                or (isinstance(f, ast.Name) and f.id in getenv_names)
                or (isinstance(f, ast.Attribute) and f.attr == "get" and is_environ(f.value))
            ):
                key, default, line = _literal_key(node.args[0]), _literal_default(node), node.lineno
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) and is_environ(node.value):
            key, line = _literal_key(node.slice), node.lineno
        if key is not None:
            found.append(GetenvFinding(key, default, f"{location}:{line}"))
    return found


def scan_packages(roots: Sequence[Path]) -> list[GetenvFinding]:
    """Scan ``*.py`` under each root; location is ``<path relative to the root's parent>:<line>``."""
    findings: list[GetenvFinding] = []
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
            for name in sorted(filenames):
                path = Path(dirpath, name)
                if not name.endswith(".py") or path.is_symlink():
                    continue
                try:
                    if path.stat().st_size > _MAX_BYTES:
                        continue
                    source = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                findings.extend(_scan_source(source, path.relative_to(root.parent).as_posix()))
    return findings
