"""Async and I/O rules over route handlers and app source: blocking calls, outbound HTTP timeouts, background work."""

from __future__ import annotations

import ast
from collections.abc import Sequence

from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.appsource import SourceIndex
from sharpit.engine.collectors.fastapi_advisor.handlers import Handler, Hit, call_name, import_aliases, own_nodes

_CONCURRENCY = "https://fastapi.tiangolo.com/async/"
_BACKGROUND = "https://fastapi.tiangolo.com/tutorial/background-tasks/"
_TIMEOUTS = "https://requests.readthedocs.io/en/latest/user/advanced/#timeouts"

SYNC_IO = RuleDefinition(
    "FASTAPI-ASYNC-001",
    "Review blocking work in sync endpoints",
    "Performance and concurrency",
    "INFO",
    "A sync def endpoint that blocks on I/O holds one of the threadpool's worker threads (40 by default) for the "
    "whole call.",
    "Keep it sync if the work is short, or make the endpoint async def with an async client for long waits.",
    _CONCURRENCY,
)
ASYNC_BLOCKING = RuleDefinition(
    "FASTAPI-ASYNC-002",
    "Blocking call inside an async endpoint",
    "Performance and concurrency",
    "HIGH",
    "A blocking call (time.sleep, requests, subprocess, file or socket I/O) inside an async def endpoint stops the "
    "event loop: every other request waits until it returns.",
    "Use the async equivalent (asyncio.sleep, httpx.AsyncClient), run the call with run_in_threadpool, or make the "
    "endpoint a plain def.",
    _CONCURRENCY,
)
HTTP_TIMEOUT = RuleDefinition(
    "FASTAPI-HTTP-001",
    "Outbound HTTP call without a timeout",
    "Web and HTTP",
    "LOW",
    "requests has no default timeout: a call to a server that stops answering hangs its worker indefinitely.",
    "Pass timeout= to every requests call, or use httpx, which defaults to 5 seconds.",
    _TIMEOUTS,
)
HEAVY_BACKGROUND = RuleDefinition(
    "FASTAPI-BG-001",
    "Review heavy work in BackgroundTasks",
    "Performance and concurrency",
    "LOW",
    "BackgroundTasks run in the same process after the response, with no retry or persistence; a task that loops "
    "or blocks competes with requests and is lost on restart.",
    "Keep background tasks short; move long or critical work to a task queue.",
    _BACKGROUND,
)
RULES = (SYNC_IO, ASYNC_BLOCKING, HTTP_TIMEOUT, HEAVY_BACKGROUND)


_BLOCKING = frozenset(
    {
        "time.sleep",
        "urllib.request.urlopen",
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        "os.system",
        "open",
        "socket.socket",
        "socket.create_connection",
    }
)
_REQUESTS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "request"})


def _is_requests(name: str) -> bool:
    module, _, verb = name.rpartition(".")
    return module == "requests" and verb in _REQUESTS


def _blocking(name: str | None) -> bool:
    return name is not None and (name in _BLOCKING or _is_requests(name))


def blocking_calls(function: ast.FunctionDef | ast.AsyncFunctionDef, aliases: dict[str, str]) -> list[str]:
    """``<call> (line N)`` for every blocking call in a function's own body."""
    found: list[str] = []
    for node in own_nodes(function):
        if isinstance(node, ast.Call):
            name = call_name(node.func, aliases)
            if _blocking(name):
                found.append(f"{name} (line {node.lineno})")
    return found


def _blocking_handlers(handlers: Sequence[Handler], *, is_async: bool) -> list[Hit]:
    hits: list[Hit] = []
    for handler in handlers:
        if handler.is_async is is_async:
            calls = blocking_calls(handler.node, import_aliases(handler.module.tree))
            if calls:
                hits.append((handler.qualname, f"{handler.where} calls {', '.join(calls)}"))
    return hits


def sync_io(handlers: Sequence[Handler]) -> list[Hit]:
    return _blocking_handlers(handlers, is_async=False)


def async_blocking(handlers: Sequence[Handler]) -> list[Hit]:
    return _blocking_handlers(handlers, is_async=True)


def _heavy(function: ast.FunctionDef | ast.AsyncFunctionDef, aliases: dict[str, str]) -> bool:
    loops = any(isinstance(n, ast.For | ast.AsyncFor | ast.While) for n in own_nodes(function))
    return loops or bool(blocking_calls(function, aliases))


def heavy_background(handlers: Sequence[Handler]) -> list[Hit]:
    hits: list[Hit] = []
    for handler in handlers:
        tree = handler.module.tree
        defined = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
        aliases = import_aliases(tree)
        heavy = [
            f"{task.id} (line {node.lineno})"
            for node in own_nodes(handler.node)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_task"
            and node.args
            and isinstance(task := node.args[0], ast.Name)
            and task.id in defined
            and _heavy(defined[task.id], aliases)
        ]
        if heavy:
            hits.append((handler.qualname, f"{handler.where} schedules {', '.join(heavy)}, which loops or blocks"))
    return hits


def http_timeout(index: SourceIndex) -> list[Hit]:
    hits: list[Hit] = []
    for module in index.modules.values():
        aliases = import_aliases(module.tree)
        calls = sorted(
            (node.lineno, name)
            for node in ast.walk(module.tree)
            if isinstance(node, ast.Call)
            and (name := call_name(node.func, aliases)) is not None
            and _is_requests(name)
            and not any(k.arg in ("timeout", None) for k in node.keywords)  # None: **kwargs may carry it
        )
        if calls:
            listed = ", ".join(f"{name} (line {line})" for line, name in calls)
            hits.append((module.name, f"{module.name}: {listed} without timeout="))
    return hits
