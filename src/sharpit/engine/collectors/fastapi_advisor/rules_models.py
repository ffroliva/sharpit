"""Model rules over app source and route metadata: Pydantic v1 API, dict responses without a response model."""

from __future__ import annotations

import ast
import typing
from collections.abc import Sequence

from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.appsource import SourceIndex
from sharpit.engine.collectors.fastapi_advisor.handlers import Handler, Hit, own_nodes

PYDANTIC_V1 = RuleDefinition(
    "FASTAPI-PYD-001",
    "Pydantic v1 API in use",
    "Configuration",
    "MEDIUM",
    "Pydantic v1 idioms (an inner class Config, orm_mode, @validator, pydantic.v1 imports, BaseSettings from "
    "pydantic) are deprecated in Pydantic v2 and removed from FastAPI's supported path.",
    "Use model_config = ConfigDict(...), from_attributes=True, @field_validator and pydantic-settings.",
    "https://docs.pydantic.dev/latest/migration/",
)
DICT_RESPONSE = RuleDefinition(
    "FASTAPI-RESP-001",
    "Endpoint returns a dict without a response model",
    "Web and HTTP",
    "LOW",
    "An endpoint that returns a plain dict with no response model is neither validated nor filtered on the way "
    "out, and its OpenAPI schema says nothing about the body.",
    "Declare a Pydantic response model (response_model= or a return annotation).",
    "https://fastapi.tiangolo.com/tutorial/response-model/",
)
RULES = (PYDANTIC_V1, DICT_RESPONSE)


_V1_NAMES = frozenset({"BaseSettings", "validator", "root_validator"})
_DICT_NAMES = frozenset({"dict", "Dict", "typing.Dict"})


def _v1_imports(tree: ast.Module) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            if node.module == "pydantic.v1" or node.module.startswith("pydantic.v1."):
                found.append((node.lineno, "pydantic.v1 import"))
            elif node.module == "pydantic":
                found.extend((node.lineno, f"from pydantic import {a.name}") for a in node.names if a.name in _V1_NAMES)
        elif isinstance(node, ast.Import):
            found.extend((node.lineno, "pydantic.v1 import") for a in node.names if a.name.startswith("pydantic.v1"))
    return found


def _v1_classes(tree: ast.Module) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for model in ast.walk(tree):
        if not isinstance(model, ast.ClassDef) or not model.bases:
            continue
        found.extend(
            (inner.lineno, f"class Config in {model.name}")
            for inner in model.body
            if isinstance(inner, ast.ClassDef) and inner.name == "Config"
        )
        for node in ast.walk(model):
            if isinstance(node, ast.keyword) and node.arg == "orm_mode":
                found.append((node.value.lineno, f"orm_mode in {model.name}"))
            elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "orm_mode" for t in node.targets
            ):
                found.append((node.lineno, f"orm_mode in {model.name}"))
    return found


def pydantic_v1(index: SourceIndex) -> list[Hit]:
    hits: list[Hit] = []
    for module in index.modules.values():
        signals = sorted({*_v1_imports(module.tree), *_v1_classes(module.tree)})
        if signals:
            listed = "; ".join(f"{what} (line {line})" for line, what in signals)
            hits.append((module.name, f"{module.name}: {listed}"))
    return hits


def _dict_annotation(node: ast.expr | None) -> bool:
    target = node.value if isinstance(node, ast.Subscript) else node
    return target is not None and ast.unparse(target) in _DICT_NAMES


def _dict_model(model: object) -> bool:
    return model is dict or typing.get_origin(model) is dict


def dict_response(handlers: Sequence[Handler]) -> list[Hit]:
    hits: list[Hit] = []
    for handler in handlers:
        if handler.response_model is not None and not _dict_model(handler.response_model):
            continue
        returns = [n for n in own_nodes(handler.node) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]
        if _dict_annotation(handler.node.returns) or returns:
            hits.append((handler.qualname, f"{handler.where} returns a dict and declares no response model"))
    return hits
