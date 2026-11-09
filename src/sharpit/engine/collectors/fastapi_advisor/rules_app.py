"""Application rules over app source and the app object's own attributes: lifecycle, error handling, settings."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Sequence

from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.appsource import ModuleInfo, SourceIndex
from sharpit.engine.collectors.fastapi_advisor.handlers import Handler, Hit
from sharpit.engine.testsession.swallowed import swallowing_lines

ON_EVENT = RuleDefinition(
    "FASTAPI-EVT-001",
    "Deprecated on_event startup and shutdown handlers",
    "Configuration",
    "LOW",
    "on_event / add_event_handler startup and shutdown hooks are deprecated in favour of a lifespan context.",
    "Move startup and shutdown work into a lifespan async context manager passed to FastAPI(lifespan=...).",
    "https://fastapi.tiangolo.com/advanced/events/",
)
BROAD_EXCEPT = RuleDefinition(
    "FASTAPI-EXC-001",
    "Broad except swallows errors in an endpoint",
    "Web and HTTP",
    "MEDIUM",
    "An endpoint catches Exception (or everything) and neither logs, re-raises nor returns an error: the client "
    "sees success and the failure leaves no trace.",
    "Catch the specific exceptions you expect, log the rest, or raise HTTPException.",
    "https://fastapi.tiangolo.com/tutorial/handling-errors/",
)
DEBUG = RuleDefinition(
    "SPRING-WEB-004",
    "Review configured fallback error details",
    "Web and HTTP",
    "MEDIUM",
    "FastAPI(debug=True) returns tracebacks to the client on an unhandled error.",
    "Leave debug off outside local development.",
    "https://www.starlette.io/applications/",
)
DEFAULT_TITLE = RuleDefinition(
    "SPRING-CONFIG-004",
    "Consider a stable application name",
    "Configuration",
    "INFO",
    "The application keeps FastAPI's default title, so its OpenAPI document and docs page name no service.",
    "Pass title= to FastAPI().",
    "https://fastapi.tiangolo.com/tutorial/metadata/",
)
RULES = (ON_EVENT, BROAD_EXCEPT, DEBUG, DEFAULT_TITLE)


_EVENT_HOOKS = frozenset({"on_event", "add_event_handler"})


def on_event(index: SourceIndex) -> list[Hit]:
    hits: list[Hit] = []
    for module in index.modules.values():
        calls = sorted(
            (node.lineno, node.func.attr)
            for node in ast.walk(module.tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _EVENT_HOOKS
        )
        if calls:
            listed = ", ".join(f"{name} (line {line})" for line, name in calls)
            hits.append((module.name, f"{module.name}: {listed}"))
    return hits


def _functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


def _swallowing_spans(module: ModuleInfo) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, list[int]]]:
    """Each function of the module with the swallowing ``except`` lines inside it.

    ``swallowing_lines`` reads source text and the index keeps trees only, so the module is unparsed once and both
    the check and the function spans read that same text; ``ast.walk`` order matches between the two trees.
    """
    text = ast.unparse(module.tree)
    lines = swallowing_lines(text)
    twins = _functions(ast.parse(text))
    return [
        (original, [line for line in lines if twin.lineno <= line <= (twin.end_lineno or twin.lineno)])
        for original, twin in zip(_functions(module.tree), twins, strict=True)
    ]


def broad_except(handlers: Sequence[Handler]) -> list[Hit]:
    spans: dict[str, list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, list[int]]]] = {}
    hits: list[Hit] = []
    for handler in handlers:
        module = handler.module
        if module.name not in spans:
            spans[module.name] = _swallowing_spans(module)
        if any(node is handler.node and lines for node, lines in spans[module.name]):
            hits.append((handler.qualname, f"{handler.where} catches Exception and discards it"))
    return hits


def _static(app: object, name: str) -> object:
    """An attribute of the app object without running a descriptor or ``__getattr__`` (``getattr_static``)."""
    return inspect.getattr_static(app, name, None)


def debug(app: object) -> list[Hit]:
    value = _static(app, "debug")
    if not isinstance(value, bool):  # Starlette versions that keep it behind a property store ``_debug``
        value = _static(app, "_debug")
    return [("app", "the application runs with debug=True")] if value is True else []


def default_title(app: object) -> list[Hit]:
    title = _static(app, "title")
    return [("app", "the application keeps the default title 'FastAPI'")] if title == "FastAPI" else []
