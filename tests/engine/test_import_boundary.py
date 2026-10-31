"""The engine remains framework-free so it can be used without FastAPI or Starlette."""

from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2] / "src" / "sharpit" / "engine"


def test_engine_modules_do_not_import_fastapi_or_starlette():
    imports: list[str] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            for child in node.orelse:
                visit(child)
            return
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names if alias.name.split(".")[0] in {"fastapi", "starlette"})
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in {"fastapi", "starlette"}:
            imports.append(node.module)
        for child in ast.iter_child_nodes(node):
            visit(child)

    for module in ENGINE.rglob("*.py"):
        visit(ast.parse(module.read_text(encoding="utf-8")))

    assert imports == []
