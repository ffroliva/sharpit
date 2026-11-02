"""Swallowed exceptions (spec 0.4.0 §5.5 F1): does the ``except`` clause that handled an exception swallow it?

A clause swallows when it catches everything, ``Exception`` or ``BaseException`` and its body neither raises nor calls
a logger or ``warnings``. Only stdlib ``ast``/``dis``: no source text, local or message is kept, and a name the parser
cannot resolve to a builtin exception counts as "may match", so an unknown clause never produces a finding.
"""

from __future__ import annotations

import ast
import builtins
import dis
import functools
import linecache
from types import CodeType

PROGRAMMING_ERRORS: tuple[type[BaseException], ...] = (
    AttributeError,
    TypeError,
    NameError,
    ImportError,
    UnboundLocalError,
)
_PUSH_EXC_INFO = dis.opmap["PUSH_EXC_INFO"]  # the first instruction of a try's handler block (CPython >= 3.11)
_BROAD = frozenset({"Exception", "BaseException"})
_LOG_CALLS = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log"})

type _Entry = tuple[tuple[ast.ExceptHandler, ...], int]  # a try's clauses and the clause at the given line


def is_programming_error(exc: BaseException) -> bool:
    return isinstance(exc, PROGRAMMING_ERRORS)


def _index(tree: ast.AST) -> dict[int, _Entry]:
    """Every line of every ``except`` clause header -> (that try's clauses, the clause's position)."""
    index: dict[int, _Entry] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            handlers = tuple(node.handlers)
            for position, handler in enumerate(handlers):
                last = handler.type.end_lineno if handler.type is not None else None
                for line in range(handler.lineno, (last or handler.lineno) + 1):
                    index.setdefault(line, (handlers, position))
    return index


def _elements(handler: ast.ExceptHandler) -> list[ast.expr]:
    kind = handler.type
    if kind is None:
        return []
    return list(kind.elts) if isinstance(kind, ast.Tuple) else [kind]


def _broad(handler: ast.ExceptHandler) -> bool:
    return handler.type is None or any(isinstance(e, ast.Name) and e.id in _BROAD for e in _elements(handler))


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else None


_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)  # bodies that do not run when the clause runs


def _silent(handler: ast.ExceptHandler) -> bool:
    pending: list[ast.AST] = list(handler.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Raise):
            return False
        if isinstance(node, ast.Call) and _call_name(node.func) in _LOG_CALLS:
            return False
        if not isinstance(node, _SCOPES):  # a class body runs; its methods are stopped here
            pending.extend(ast.iter_child_nodes(node))
    return True


def _catches(handler: ast.ExceptHandler, exc_type: type[BaseException]) -> bool | None:
    """True/False when every name is a builtin exception; None when an unresolvable name may match."""
    if handler.type is None:
        return True
    unknown = False
    for element in _elements(handler):
        candidate = getattr(builtins, element.id, None) if isinstance(element, ast.Name) else None
        if not (isinstance(candidate, type) and issubclass(candidate, BaseException)):
            unknown = True
        elif issubclass(exc_type, candidate):
            return True
    return None if unknown else False


def _swallowing(entry: _Entry, exc_type: type[BaseException] | None) -> ast.ExceptHandler | None:
    """The clause that handled ``exc_type`` (the one at the entry's line without it) when it swallows, else None."""
    handlers, position = entry
    handler = handlers[position]
    if exc_type is not None:  # CPython tries the clauses in order: find the one that handled it
        for candidate in handlers:
            matched = _catches(candidate, exc_type)
            if matched is None:
                return None
            if matched:
                handler = candidate
                break
        else:
            return None
    return handler if _broad(handler) and _silent(handler) else None


def handler_swallows(source: str, handled_line: int, exc: BaseException | None = None) -> bool:
    """Whether the try with a clause header on ``handled_line`` swallows: ``exc`` picks the matching clause, without it
    the clause on that line is judged."""
    entry = _index(ast.parse(source)).get(handled_line)
    return entry is not None and _swallowing(entry, None if exc is None else type(exc)) is not None


@functools.lru_cache(maxsize=256)
def _file_index(filename: str) -> dict[int, _Entry]:
    source = "".join(linecache.getlines(filename))
    try:
        return _index(ast.parse(source)) if source else {}
    except (SyntaxError, ValueError):
        return {}


@functools.lru_cache(maxsize=4096)
def _entry(code: CodeType, offset: int) -> _Entry | None:
    """The try whose handler block starts at ``offset``; None for cleanup blocks, ``with`` exits and anything else."""
    raw = code.co_code
    if not 0 <= offset < len(raw) or raw[offset] != _PUSH_EXC_INFO:
        return None
    # the entry instruction has no line; the next one with a line is the first clause's header
    line = next((line for _, end, line in code.co_lines() if end > offset + 2 and line is not None), None)
    return None if line is None else _file_index(code.co_filename).get(line)


@functools.lru_cache(maxsize=4096)
def swallowing_clause_line(code: CodeType, offset: int, exc_type: type[BaseException] | None) -> int | None:
    """The header line of the clause that swallowed an ``EXCEPTION_HANDLED`` event's exception, None when none did."""
    entry = _entry(code, offset)
    handler = None if entry is None else _swallowing(entry, exc_type)
    return None if handler is None else handler.lineno


def handler_swallows_code(code: CodeType, offset: int, exc: BaseException | None = None) -> bool:
    """``handler_swallows`` for an ``EXCEPTION_HANDLED`` event's code object and instruction offset (cached)."""
    return swallowing_clause_line(code, offset, None if exc is None else type(exc)) is not None


def swallowing_lines(source: str) -> list[int]:
    """The header lines of every broad, silent ``except`` clause in a module's source (the static check)."""
    found = {
        handler.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Try)
        for handler in node.handlers
        if _broad(handler) and _silent(handler)
    }
    return sorted(found)


def clear_cache() -> None:
    for cached in (_file_index, _entry, swallowing_clause_line):
        cached.cache_clear()
