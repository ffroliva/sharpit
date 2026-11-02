"""Swallowed exceptions (spec 0.4.0 §5.5 F1): does the ``except`` clause that handled an exception swallow it?"""

from __future__ import annotations

from types import CodeType

PROGRAMMING_ERRORS: tuple[type[BaseException], ...] = ()


def is_programming_error(exc: BaseException) -> bool:
    return False


def handler_swallows(source: str, handled_line: int, exc: BaseException | None = None) -> bool:
    return False


def handler_swallows_code(code: CodeType, offset: int, exc: BaseException | None = None) -> bool:
    return False


def swallowing_lines(source: str) -> list[int]:
    return []
