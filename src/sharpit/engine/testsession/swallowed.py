"""Swallowed exceptions (spec 0.4.0 §5.5 F1): does the ``except`` clause that handled an exception swallow it?

A clause swallows when it catches everything, ``Exception`` or ``BaseException`` and its body neither raises, returns
an HTTP error response nor calls a recognised sink: a logger, ``warnings``, an error tracker, or a function of the same
module whose own body does one of those. Only stdlib ``ast``/``dis``: no source text, local or message is kept, and a
name the parser cannot resolve to a builtin exception counts as "may match", so an unknown clause never produces a
finding.
"""

from __future__ import annotations

import ast
import builtins
import dis
import functools
import linecache
from types import CodeType
from typing import NamedTuple

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
# a log call's receiver chain names one of these (``self.logger``, ``logging.getLogger(__name__)``, ``log.bind(x=1)``)
_LOGGERS = frozenset(
    {"log", "logger", "_log", "_logger", "LOG", "LOGGER", "logging", "warnings", "getLogger", "get_logger"}
)
# error-tracker captures that count as handling, kept small: by attribute anywhere, or by dotted name
_CAPTURE = "capture_exception"  # sentry_sdk.capture_exception, hub.capture_exception, a bare imported capture_exception
_TRACKERS = frozenset({"rollbar.report_exc_info", "bugsnag.notify"})
_SELF = frozenset({"self", "cls"})


class _Module(NamedTuple):
    loggers: frozenset[str]  # module-level names bound to a logger
    defined: frozenset[str]  # every function and method name defined in the module
    handling: frozenset[str]  # the defined ones whose own body raises, logs or calls a tracker
    imported: frozenset[str]  # names bound by an import


# a try's clauses, the clause at the given line and the facts about its module
type _Entry = tuple[tuple[ast.ExceptHandler, ...], int, _Module]


def is_programming_error(exc: BaseException) -> bool:
    return isinstance(exc, PROGRAMMING_ERRORS)


def _index(tree: ast.AST) -> dict[int, _Entry]:
    """Every line of every ``except`` clause header -> (that try's clauses, the clause's position)."""
    index: dict[int, _Entry] = {}
    module = _module(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            handlers = tuple(node.handlers)
            for position, handler in enumerate(handlers):
                last = handler.type.end_lineno if handler.type is not None else None
                for line in range(handler.lineno, (last or handler.lineno) + 1):
                    index.setdefault(line, (handlers, position, module))
    return index


def _module_loggers(tree: ast.AST) -> frozenset[str]:
    """Module-level names assigned from a logger factory or ``loguru.logger`` (``_audit = logging.getLogger(...)``)."""
    names: set[str] = set()
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
            value = node.value.func if isinstance(node.value, ast.Call) else node.value
            if _call_name(value) in {"getLogger", "get_logger", "logger"}:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names |= {target.id for target in targets if isinstance(target, ast.Name)}
    return frozenset(names)


def _module(tree: ast.AST) -> _Module:
    loggers = _module_loggers(tree)
    nodes = list(ast.walk(tree))
    functions = [n for n in nodes if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
    imported = {
        (alias.asname or alias.name).split(".")[0]
        for n in nodes
        if isinstance(n, ast.Import | ast.ImportFrom)
        for alias in n.names
    }
    handling = {f.name for f in functions if any(_reports(n, loggers) for n in ast.walk(f))}  # one level: no call chase
    return _Module(loggers, frozenset(f.name for f in functions), frozenset(handling), frozenset(imported))


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


def _logs(func: ast.expr, loggers: frozenset[str]) -> bool:
    """A logging call: a log method on a logger (not ``response.error(...)``), or a bare ``warn(...)``-style name."""
    if not isinstance(func, ast.Attribute):
        return _call_name(func) in _LOG_CALLS
    if func.attr not in _LOG_CALLS:
        return False
    receiver = func.value
    while isinstance(receiver, ast.Attribute | ast.Call):
        if isinstance(receiver, ast.Attribute) and receiver.attr in _LOGGERS:
            return True
        receiver = receiver.func if isinstance(receiver, ast.Call) else receiver.value
    return isinstance(receiver, ast.Name) and (receiver.id in _LOGGERS or receiver.id in loggers)


def _dotted(func: ast.expr) -> str | None:
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return _call_name(func)


def _tracks(func: ast.expr) -> bool:
    """An error-tracker capture (Sentry, Rollbar, Bugsnag)."""
    return _call_name(func) == _CAPTURE or _dotted(func) in _TRACKERS


def _reports(node: ast.AST, loggers: frozenset[str]) -> bool:
    """A raise, or a call to a logger, ``warnings`` or an error tracker."""
    return isinstance(node, ast.Raise) or (
        isinstance(node, ast.Call) and (_logs(node.func, loggers) or _tracks(node.func))
    )


def _passes(call: ast.Call, bound: str | None) -> bool:
    """The call hands the caught exception on (``self._report(e)``)."""
    arguments = [*call.args, *(keyword.value for keyword in call.keywords)]
    return bound is not None and any(isinstance(a, ast.Name) and a.id == bound for a in arguments)


def _hands_on(func: ast.expr, module: _Module) -> bool:
    """A call handing the exception on handles it when its target, a function of this module, reports; a builtin or a
    method on a local value (``errors.append(e)``, ``str(e)``) does not."""
    name = _call_name(func)
    if name in module.defined:
        return name in module.handling
    # fail-safe (0.4.0): an imported, inherited or dynamic target cannot be read here, so never report on a guess
    if isinstance(func, ast.Name):
        return not hasattr(builtins, func.id)
    if isinstance(func, ast.Attribute):
        return isinstance(func.value, ast.Name) and (func.value.id in _SELF or func.value.id in module.imported)
    return True  # getattr(self, name)(e), handlers[kind](e), ...


def _http_error(value: ast.expr) -> bool:
    """A statically visible status code >= 400: ``500`` or ``status.HTTP_503_SERVICE_UNAVAILABLE``."""
    if isinstance(value, ast.Constant):
        return isinstance(value.value, int) and value.value >= 400
    code = (_call_name(value) or "").removeprefix("HTTP_")[:3]
    return code.isdigit() and int(code) >= 400


def _error_response(node: ast.AST) -> bool:
    """``return JSONResponse(..., status_code=500)``: the failure reaches the client."""
    call = node.value if isinstance(node, ast.Return) else None
    return isinstance(call, ast.Call) and any(k.arg == "status_code" and _http_error(k.value) for k in call.keywords)


def _handles(node: ast.AST, bound: str | None, module: _Module) -> bool:
    if _reports(node, module.loggers) or _error_response(node):
        return True
    return isinstance(node, ast.Call) and _passes(node, bound) and _hands_on(node.func, module)


def _unreferenced(node: ast.AST, used: set[str]) -> bool:
    """A nested scope whose body cannot run while the clause runs: a def (or a lambda bound only to names) the clause
    never references. A referenced one may be called, awaited or passed on: it is followed, so a doubt never reports."""
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return node.name not in used
    return (
        isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Lambda)
        and all(isinstance(target, ast.Name) and target.id not in used for target in node.targets)
    )


def _silent(handler: ast.ExceptHandler, module: _Module) -> bool:
    nodes = list(ast.walk(handler))
    used = {n.id for n in nodes if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    used |= {n.attr for n in nodes if isinstance(n, ast.Attribute)}  # a class method called as obj.method()
    pending: list[ast.AST] = list(handler.body)
    while pending:
        node = pending.pop()
        if _handles(node, handler.name, module):
            return False
        if not _unreferenced(node, used):
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
    handlers, position, module = entry
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
    return handler if _broad(handler) and _silent(handler, module) else None


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
    tree = ast.parse(source)
    module = _module(tree)
    found = {
        handler.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        for handler in node.handlers
        if _broad(handler) and _silent(handler, module)
    }
    return sorted(found)


def clear_cache() -> None:
    for cached in (_file_index, _entry, swallowing_clause_line):
        cached.cache_clear()
