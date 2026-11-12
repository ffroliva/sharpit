"""REST API error-contract catalogue built from exception-handler declarations."""

from __future__ import annotations

import ast
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sharpit.engine.appsource import ModuleInfo, SourceIndex
from sharpit.engine.collectors.restapi.rules_common import FRAMEWORK_MODULES
from sharpit.engine.paging import paged
from sharpit.engine.spi import ApiModel, ErrorHandlerInfo

DEFAULT_MAX_ENTRIES = 500


@dataclass(frozen=True)
class ErrorContractEntry:
    id: str
    exception_type: str
    exception_simple_name: str
    component: str
    component_simple_name: str
    method: str
    source: str
    scope: str
    scope_target: str | None
    precedence: int
    precedence_source: str
    status: str | None
    status_source: str
    body_category: str
    body_type: str | None
    produces: tuple[str, ...]

    def dto(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "exceptionType": self.exception_type,
            "exceptionSimpleName": self.exception_simple_name,
            "component": self.component,
            "componentSimpleName": self.component_simple_name,
            "method": self.method,
            "source": self.source,
            "scope": self.scope,
            "scopeTarget": self.scope_target,
            "precedence": self.precedence,
            "precedenceSource": self.precedence_source,
            "status": self.status,
            "statusSource": self.status_source,
            "bodyCategory": self.body_category,
            "bodyType": self.body_type,
            "produces": list(self.produces),
        }


def _simple(name: str) -> str:
    return name.rpartition(".")[2]


def _split_handler(handler: str, index: SourceIndex | None) -> tuple[str, str]:
    if index is not None:
        module = next(
            (name for name in sorted(index.modules, key=len, reverse=True) if handler.startswith(name + ".")), None
        )
        if module is not None:
            return module, handler[len(module) + 1 :]
    return handler.rpartition(".")[0], handler.rpartition(".")[2]


def _handler_node(
    handler: str, index: SourceIndex | None
) -> tuple[ModuleInfo | None, ast.FunctionDef | ast.AsyncFunctionDef | None]:
    if index is None:
        return None, None
    module_name, qualname = _split_handler(handler, index)
    module = index.modules.get(module_name)
    if module is None:
        return None, None
    parts = [p for p in qualname.split(".") if p != "<locals>"]
    body = module.tree.body
    node = None
    for part in parts:
        node = next(
            (
                item
                for item in body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and item.name == part
            ),
            None,
        )
        if node is None:
            break
        body = node.body
    if isinstance(node, ast.ClassDef):
        node = None
    return module, node


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _dict_category(value: ast.Dict) -> str:
    keys = {key.value for key in value.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)}
    return "PROBLEM_DETAIL" if {"type", "title", "status"} <= keys else "CUSTOM_OBJECT"


def _body(value: ast.expr) -> tuple[str, str | None]:
    if not isinstance(value, ast.Call):
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return "STRING", "str"
        if isinstance(value, ast.Dict):
            return _dict_category(value), "dict"
        return "DYNAMIC", None
    name = _call_name(value.func)
    keywords = {keyword.arg: keyword.value for keyword in value.keywords if keyword.arg}
    content = keywords.get("content") or (value.args[0] if value.args else None)
    if name == "JSONResponse" and isinstance(content, ast.Dict):
        return _dict_category(content), "dict"
    if name == "PlainTextResponse" or isinstance(content, ast.Constant) and isinstance(content.value, str):
        return "STRING", "str"
    if name == "Response" and content is None:
        return "EMPTY", None
    return "DYNAMIC", None


def _status(value: ast.expr, current: str | None, source: str) -> tuple[str | None, str]:
    if not isinstance(value, ast.Call):
        return current, source
    declared = next((keyword.value for keyword in value.keywords if keyword.arg == "status_code"), None)
    if (
        declared is None
        and _call_name(value.func) in {"JSONResponse", "Response", "PlainTextResponse"}
        and len(value.args) > 1
    ):
        declared = value.args[1]
    if isinstance(declared, ast.Constant) and type(declared.value) is int:
        return str(declared.value), "ANNOTATION"
    return (None, "DYNAMIC") if declared is not None else (current, source)


def _declaration(info: ErrorHandlerInfo, index: SourceIndex | None) -> tuple[str | None, str, str, str | None]:
    if getattr(info, "is_partial", False):
        return None, "UNRESOLVED", "UNRESOLVED", None
    _, function = _handler_node(info.handler, index)
    status = str(info.key_status) if info.key_status is not None else None
    status_source = "ANNOTATION" if status is not None else "DYNAMIC"
    if function is None:
        return status, status_source if status is not None else "UNRESOLVED", "UNRESOLVED", None
    category, body_type = "UNRESOLVED", None
    returns = [node.value for node in ast.walk(function) if isinstance(node, ast.Return) and node.value is not None]
    for value in returns:
        status, status_source = _status(value, status, status_source)
        category, body_type = _body(value)
        if category != "DYNAMIC" or isinstance(value, ast.Call):
            break
    return status, status_source, category, body_type


def _scope_rank(scope: str) -> int:
    return 1 if scope == "SCOPED" else 2


def _rank_group(
    candidates: list[tuple[ErrorHandlerInfo, str, str, str]],
    index: SourceIndex | None,
) -> list[ErrorContractEntry]:
    ordered = sorted(
        candidates,
        key=lambda c: (_scope_rank(c[0].scope), c[2], c[3]),
    )
    ranked: list[ErrorContractEntry] = []
    i = 0
    while i < len(ordered):
        end = i + 1
        while end < len(ordered) and _scope_rank(ordered[i][0].scope) == _scope_rank(ordered[end][0].scope):
            end += 1
        rank = i + 1
        for pos in range(i, end):
            info, exception_type, component, method = ordered[pos]
            status, status_source, category, body_type = _declaration(info, index)
            ranked.append(
                ErrorContractEntry(
                    f"{component}#{method}({exception_type})",
                    exception_type,
                    _simple(exception_type),
                    component,
                    _simple(component),
                    method,
                    "STARLETTE_EXCEPTION_HANDLER",
                    info.scope,
                    info.scope_target,
                    rank,
                    "DEFAULT",
                    status,
                    status_source,
                    category,
                    body_type,
                    (),
                )
            )
        i = end
    return ranked


def index_for_handlers(handlers: Sequence[ErrorHandlerInfo]) -> SourceIndex:
    """Build a minimal SourceIndex from the modules defining each handler, read from disk."""
    modules: dict[str, ModuleInfo] = {}
    for info in handlers:
        parts = info.handler.split(".")
        for i in range(len(parts), 0, -1):
            mod_name = ".".join(parts[:i])
            if mod_name in sys.modules:
                mod = sys.modules[mod_name]
                filename = getattr(mod, "__file__", None)
                if isinstance(filename, str) and filename.endswith(".py") and mod_name not in modules:
                    try:
                        source = Path(filename).read_text("utf-8")
                        tree = ast.parse(source)
                        modules[mod_name] = ModuleInfo(mod_name, Path(filename), tree, (), ())
                    except (OSError, SyntaxError, ValueError):
                        pass
                break
    return SourceIndex(modules=modules)


def entries(model: ApiModel, index: SourceIndex | None = None) -> list[ErrorContractEntry]:
    """One sorted entry per declared key, with all handler details derived from source AST only."""
    if index is None:
        index = index_for_handlers(model.error_handlers)
    by_exception: dict[str, list[tuple[ErrorHandlerInfo, str, str, str]]] = {}
    for info in model.error_handlers:
        component, method = _split_handler(info.handler, index)
        if component.split(".", 1)[0] in FRAMEWORK_MODULES:
            continue
        exception_type = info.key_type or (f"status={info.key_status}" if info.key_status is not None else "unknown")
        by_exception.setdefault(exception_type, []).append((info, exception_type, component, method))
    result: list[ErrorContractEntry] = []
    for group in by_exception.values():
        result.extend(_rank_group(group, index))
    result.sort(
        key=lambda entry: (
            entry.exception_simple_name,
            entry.exception_type,
            entry.precedence,
            entry.component,
            entry.method,
        )
    )
    return result


def error_contract_report(
    model: ApiModel, index: SourceIndex | None, q: str | None, offset: int, limit: int | None
) -> dict[str, Any]:
    """Return the BootUI-shaped bounded catalogue and a server-side filtered page."""
    all_entries = entries(model, index)
    truncated = len(all_entries) > DEFAULT_MAX_ENTRIES
    bounded = all_entries[:DEFAULT_MAX_ENTRIES]
    page, metadata = paged(
        bounded,
        q,
        offset,
        limit,
        lambda entry: (
            entry.exception_type,
            entry.component,
            entry.method,
            entry.status,
            entry.scope,
            entry.body_category,
            entry.body_type,
            ", ".join(entry.produces),
        ),
    )
    return {
        "available": True,
        "unavailableReason": None,
        "total": len(bounded),
        "handlerCount": len({f"{entry.component}#{entry.method}" for entry in bounded}),
        "componentCount": len({entry.component for entry in bounded}),
        "exceptionTypeCount": len({entry.exception_type for entry in bounded}),
        "truncated": truncated,
        "maxEntries": DEFAULT_MAX_ENTRIES,
        "entries": [entry.dto() for entry in page],
        "page": metadata,
    }
