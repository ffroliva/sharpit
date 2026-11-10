"""Deprecated-use matching checks calls and attribute calls, not decorators, bases or annotations.

Only AST Call nodes are scanned, so bare attribute reads are not matched.
"""

from __future__ import annotations

import ast
from importlib.util import resolve_name

from sharpit.engine.advisors.findings import Finding
from sharpit.engine.appsource import SourceIndex
from sharpit.engine.collectors.architecture.common import ADVISOR


def _import_aliases(tree: ast.Module, modules_to_match: set[str], symbol: str) -> tuple[set[str], set[str]]:
    direct: set[str] = set()
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in modules_to_match:
            direct.update(alias.asname or alias.name for alias in node.names if alias.name == symbol)
        elif isinstance(node, ast.Import):
            modules.update(alias.asname or alias.name for alias in node.names if alias.name in modules_to_match)
    return direct, modules


def _frozen_model_config(node: ast.ClassDef) -> bool:
    for statement in node.body:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            if not any(isinstance(target, ast.Name) and target.id == "model_config" for target in targets):
                continue
            value = statement.value
            if isinstance(value, ast.Dict):
                return any(
                    isinstance(key, ast.Constant)
                    and key.value == "frozen"
                    and isinstance(item, ast.Constant)
                    and item.value is True
                    for key, item in zip(value.keys, value.values, strict=True)
                )
            if isinstance(value, ast.Call):
                return any(
                    keyword.arg == "frozen" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
                    for keyword in value.keywords
                )
    return False


def _settings_imports(tree: ast.Module) -> tuple[set[str], set[str]]:
    return _import_aliases(tree, {"pydantic_settings"}, "BaseSettings")


def _settings_fields(node: ast.ClassDef) -> list[tuple[str, int]]:
    return [field for statement in node.body if (field := _settings_field(statement)) is not None]


def _settings_field(node: ast.stmt) -> tuple[str, int] | None:
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and not _class_var(node.annotation):
        return node.target.id, node.lineno
    return None


def _class_var(annotation: ast.expr) -> bool:
    value = annotation.value if isinstance(annotation, ast.Subscript) else annotation
    return (isinstance(value, ast.Name) and value.id == "ClassVar") or (
        isinstance(value, ast.Attribute) and value.attr == "ClassVar"
    )


def _class_map(index: SourceIndex) -> dict[str, tuple[str, ast.ClassDef]]:
    return {
        f"{module}.{node.name}": (module, node)
        for module, info in index.modules.items()
        for node in info.tree.body
        if isinstance(node, ast.ClassDef)
    }


def _is_settings_class(
    qualname: str, classes: dict[str, tuple[str, ast.ClassDef]], index: SourceIndex, seen: set[str]
) -> bool:
    if qualname in seen or qualname not in classes:
        return False
    seen.add(qualname)
    module, node = classes[qualname]
    info = index.modules[module]
    direct, aliases = _settings_imports(info.tree)
    imported = {
        alias.asname or alias.name: f"{_resolved_import(statement, module)}.{alias.name}"
        for statement in info.tree.body
        if isinstance(statement, ast.ImportFrom)
        for alias in statement.names
    }
    for base in node.bases:
        name = ast.unparse(base)
        if name in direct or (name.endswith(".BaseSettings") and name.split(".")[0] in aliases):
            return True
        if _is_settings_class(imported.get(name, f"{module}.{name}"), classes, index, seen):
            return True
    return False


def eval_settings(index: SourceIndex, out: dict[str, list[Finding]]) -> None:
    classes = _class_map(index)
    settings = {name for name in classes if _is_settings_class(name, classes, index, set())}
    for mod_name, info in index.modules.items():
        for node in info.tree.body:
            if not isinstance(node, ast.ClassDef) or f"{mod_name}.{node.name}" not in settings:
                continue
            if _frozen_model_config(node):
                continue
            for name, line in _settings_fields(node):
                out.setdefault("ARCH-SPRING-015", []).append(
                    Finding(
                        "ARCH-SPRING-015",
                        ADVISOR,
                        "INFO",
                        f"{mod_name}:{line}",
                        f"{mod_name}:{line} mutable settings field {name}",
                    )
                )


def _deprecated_decorator_names(tree: ast.Module) -> set[str]:
    direct, modules = _import_aliases(tree, {"warnings", "typing_extensions"}, "deprecated")
    return direct | {f"{module}.deprecated" for module in modules}


def _decorated_names(tree: ast.Module, decorators: set[str]) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for decorator in node.decorator_list:
            value = decorator.func if isinstance(decorator, ast.Call) else decorator
            if ast.unparse(value) in decorators:
                names.add(node.name)
    return names


def _resolved_import(statement: ast.ImportFrom, module_name: str) -> str:
    if not statement.level:
        return statement.module or ""
    package = module_name.rpartition(".")[0]
    return resolve_name("." * statement.level + (statement.module or ""), package)


def _deprecated_import_names(tree: ast.Module, module_name: str, deprecated: dict[str, set[str]]) -> set[str]:
    names: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom):
            module = _resolved_import(statement, module_name)
            names.update(
                alias.asname or alias.name for alias in statement.names if alias.name in deprecated.get(module, set())
            )
            for alias in statement.names:
                target = f"{module}.{alias.name}"
                names.update(f"{alias.asname or alias.name}.{name}" for name in deprecated.get(target, set()))
        elif isinstance(statement, ast.Import):
            for alias in statement.names:
                names.update(f"{alias.asname or alias.name}.{name}" for name in deprecated.get(alias.name, set()))
    return names


def _deprecated_calls(tree: ast.Module, names: set[str]) -> list[int]:
    lines = {node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call) and ast.unparse(node.func) in names}
    return sorted(lines)


def eval_deprecated(index: SourceIndex, out: dict[str, list[Finding]]) -> None:
    deprecated = {
        name: _decorated_names(info.tree, _deprecated_decorator_names(info.tree))
        for name, info in index.modules.items()
    }
    for mod_name, info in index.modules.items():
        names = _deprecated_import_names(info.tree, mod_name, deprecated)
        names.update(deprecated.get(mod_name, set()))
        for line in _deprecated_calls(info.tree, names):
            out.setdefault("ARCH-CODE-009", []).append(
                Finding(
                    "ARCH-CODE-009",
                    ADVISOR,
                    "INFO",
                    f"{mod_name}:{line}",
                    f"{mod_name}:{line} uses deprecated app symbol",
                )
            )
