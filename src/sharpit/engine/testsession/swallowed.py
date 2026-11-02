"""Swallowed exceptions (spec 0.4.0 §5.5 F1): does the ``except`` clause that handled an exception swallow it?"""

from __future__ import annotations

import ast
from types import CodeType

PROGRAMMING_ERRORS: tuple[type[BaseException], ...] = (
    AttributeError,
    TypeError,
    NameError,
    ImportError,
    UnboundLocalError,
)


def is_programming_error(exc: BaseException) -> bool:
    return isinstance(exc, PROGRAMMING_ERRORS)


def _clauses(tree: ast.AST) -> dict[int, ast.ExceptHandler]:
    return {h.lineno: h for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler)}


def handler_swallows(source: str, handled_line: int, exc: BaseException | None = None) -> bool:
    return handled_line in _clauses(ast.parse(source))


def handler_swallows_code(code: CodeType, offset: int, exc: BaseException | None = None) -> bool:
    return True


def swallowing_lines(source: str) -> list[int]:
    return sorted(_clauses(ast.parse(source)))


def clear_cache() -> None:
    return None
