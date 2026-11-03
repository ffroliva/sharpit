"""Every patch on an ``engine/sqla`` module hits the code that runs (0.5.0 spec §4.1, plan F5b Task 1).

A patch replaces one module attribute, so it changes behaviour only for callers that look the name up through that
module at call time: a bare name inside the module, or ``module.name`` from another module. A caller holding its own
binding (``from module import name``, a package re-export of a submodule's function, a reference captured at import)
never sees the patch, and the test relying on it passes for the wrong reason. Splitting ``engine/sqla.py`` into a
package creates exactly those second bindings, so every ``monkeypatch.setattr``/``mock.patch`` target in ``tests/``
that is a ``sharpit.engine.sqla*`` module is checked against every caller under ``src/sharpit``.
"""

from __future__ import annotations

import ast
import builtins
import functools
import importlib
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"
PACKAGE = "sharpit.engine.sqla"
_MISSING = object()


@dataclass(frozen=True)
class Patch:
    where: str  # tests/<file>.py:<line>
    module: ModuleType
    name: str


@dataclass(frozen=True)
class Use:
    where: str  # src/<file>.py:<line>
    namespace: str  # the module the name is looked up through
    at_import: bool  # evaluated once at import (a captured reference), not at call time


@functools.cache
def _tree(path: Path) -> ast.Module:
    with warnings.catch_warnings():  # a test file's invalid escape in a string is not this check's business
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(path.read_text(encoding="utf-8"))


def _module_name(path: Path) -> str:
    parts = path.relative_to(SRC).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _aliases(tree: ast.Module, module: str = "", is_package: bool = False) -> dict[str, str]:
    """Local name -> the dotted path it was imported as, from every import in the file (relative ones resolved)."""
    package = module if is_package else module.rpartition(".")[0]
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                found[local] = alias.name if alias.asname else local
        elif isinstance(node, ast.ImportFrom):
            base = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
            origin = node.module if not node.level else ".".join(p for p in (base, node.module) if p)
            for alias in node.names:
                found[alias.asname or alias.name] = f"{origin}.{alias.name}"
    return found


def _load(dotted: str) -> object:
    """The module ``dotted`` names, or the attribute its last part names; only sharpit's own modules are imported."""
    if dotted.split(".")[0] != "sharpit":
        return _MISSING
    try:
        return importlib.import_module(dotted)
    except ImportError:
        parent, _, attr = dotted.rpartition(".")
        try:
            return getattr(importlib.import_module(parent), attr, _MISSING)
        except ImportError:
            return _MISSING


def _resolve(expr: ast.expr, aliases: dict[str, str]) -> object:
    parts: list[str] = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if not isinstance(expr, ast.Name) or expr.id not in aliases:
        return _MISSING
    found = _load(aliases[expr.id])
    for part in reversed(parts):
        found = getattr(found, part, _MISSING)
    return found


def _is_sqla(found: object) -> bool:
    return isinstance(found, ModuleType) and (found.__name__ == PACKAGE or found.__name__.startswith(f"{PACKAGE}."))


def _patch_args(call: ast.Call) -> tuple[ast.expr, str] | str | None:
    """``(target, name)`` for ``x.setattr(target, "name")``/``patch.object(target, "name")``, a dotted string for
    ``x.setattr("a.b.name", v)``/``patch("a.b.name")``, else None."""
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
    args = call.args
    first = args[0] if args else None
    if name in ("setattr", "object") and len(args) >= 2:
        second = args[1]
        if isinstance(second, ast.Constant) and isinstance(second.value, str):
            return first, second.value  # type: ignore[return-value]
    if name in ("setattr", "patch") and isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def sqla_patches(root: Path = TESTS) -> list[Patch]:
    found: list[Patch] = []
    for path in sorted(root.rglob("*.py")):
        tree = _tree(path)
        aliases = _aliases(tree)
        for node in ast.walk(tree):
            target = _patch_args(node) if isinstance(node, ast.Call) else None
            if target is None:
                continue
            if isinstance(target, str):
                module, name = _load(target.rpartition(".")[0]), target.rpartition(".")[2]
            else:
                module, name = _resolve(target[0], aliases), target[1]
            if _is_sqla(module):
                where = f"{path.relative_to(ROOT).as_posix()}:{node.lineno}"
                found.append(Patch(where, module, name))  # type: ignore[arg-type]
    return found


def _scoped(tree: ast.Module) -> Iterator[tuple[ast.AST, bool]]:
    """Every node with whether it runs at import (module and class bodies, defaults) rather than at call time."""
    stack: list[tuple[ast.AST, bool]] = [(tree, True)]
    while stack:
        node, at_import = stack.pop()
        yield node, at_import
        body = node.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) else ()
        lazy = {id(child) for child in (body if isinstance(body, list) else [body])}
        stack.extend((child, at_import and id(child) not in lazy) for child in ast.iter_child_nodes(node))


def _top_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(t.id for t in targets if isinstance(t, ast.Name))
    return names


def uses(name: str, original: object) -> list[Use]:
    """Every load of ``original`` under ``name`` in ``src/sharpit``, with the module it is looked up through."""
    found: list[Use] = []
    for path in sorted((SRC / "sharpit").rglob("*.py")):
        module = _module_name(path)
        tree = _tree(path)
        aliases = _aliases(tree, module, path.name == "__init__.py")
        bound_here = name in aliases and _load(aliases[name]) is original
        defined_here = name in _top_level_names(tree) and module.startswith(PACKAGE)
        bound_here = bound_here or (defined_here and getattr(_load(module), name, None) is original)
        where = path.relative_to(ROOT).as_posix()
        for node, at_import in _scoped(tree):
            if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load) and bound_here:
                found.append(Use(f"{where}:{node.lineno}", module, at_import))
            elif isinstance(node, ast.Attribute) and node.attr == name and isinstance(node.ctx, ast.Load):
                owner = _resolve(node.value, aliases)
                if isinstance(owner, ModuleType) and getattr(owner, name, _MISSING) is original:
                    found.append(Use(f"{where}:{node.lineno}", owner.__name__, at_import))
    return found


def _builtin_misses(patch: Patch) -> list[str]:
    path = Path(patch.module.__file__ or "")
    used = any(isinstance(n, ast.Name) and n.id == patch.name for n in ast.walk(_tree(path)))
    return [] if used else [f"{patch.where}: {patch.module.__name__} never uses the builtin {patch.name!r}"]


def misses(patch: Patch) -> list[str]:
    """Why ``patch`` does not reach every caller of the name it replaces (empty when it does)."""
    target = patch.module.__name__
    original = patch.module.__dict__.get(patch.name, _MISSING)
    if original is _MISSING:
        if hasattr(builtins, patch.name):  # raising=False shadows a builtin for that module's own lookups only
            return _builtin_misses(patch)
        return [f"{patch.where}: {target} has no attribute {patch.name!r}"]
    found = uses(patch.name, original)
    if not found:
        return [f"{patch.where}: nothing under src/sharpit uses {target}.{patch.name}"]
    return [
        f"{patch.where} patches {target}.{patch.name}; {use.where} "
        + (f"looks it up through {use.namespace}" if use.namespace != target else "captured it at import")
        for use in found
        if use.namespace != target or use.at_import
    ]


def test_patch_targets_are_defined_where_called() -> None:
    patches = sqla_patches()
    problems = [problem for patch in patches for problem in misses(patch)]

    assert patches, "the scan found no patch on sharpit.engine.sqla*: the check would prove nothing"
    assert problems == []
