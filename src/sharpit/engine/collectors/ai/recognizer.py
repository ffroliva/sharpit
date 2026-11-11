from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _string(attributes: Mapping[str, Any], key: str) -> str | None:
    value = attributes.get(key)
    return value if isinstance(value, str) else None


def _tokens(attributes: Mapping[str, Any], key: str) -> int | None:
    value = attributes.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def operation(attributes: Mapping[str, Any], name: str) -> str | None:
    op = (_string(attributes, "gen_ai.operation.name") or "").lower()
    if op in {"chat", "text_completion"}:
        return "chat"
    if op == "embeddings":
        return "embeddings"
    if op in {"execute_tool", "tool"} or name.startswith(("spring.ai.tool", "execute_tool")):
        return "tool"
    db = (_string(attributes, "db.system") or "").lower()
    kind = (_string(attributes, "spring.ai.kind") or "").lower()
    if (
        kind == "vector_store"
        or op == "retrieval"
        or db.startswith("spring_ai")
        or "vector" in db
        or (
            _string(attributes, "db.operation.name") is not None
            and _string(attributes, "db.collection.name") is not None
            and "vectorstore" in name.lower()
        )
    ):
        return "retrieval"
    return None


def provider(attributes: Mapping[str, Any]) -> str | None:
    value = _string(attributes, "gen_ai.provider.name")
    return value if value and value.strip() else _string(attributes, "gen_ai.system")


def request_model(attributes: Mapping[str, Any]) -> str | None:
    return _string(attributes, "gen_ai.request.model") or _string(attributes, "gen_ai.request.model_name")


def response_model(attributes: Mapping[str, Any]) -> str | None:
    return _string(attributes, "gen_ai.response.model") or _string(attributes, "gen_ai.response.model_name")


def input_tokens(attributes: Mapping[str, Any]) -> int | None:
    value = _tokens(attributes, "gen_ai.usage.input_tokens")
    return value if value is not None else _tokens(attributes, "gen_ai.usage.prompt_tokens")


def output_tokens(attributes: Mapping[str, Any]) -> int | None:
    value = _tokens(attributes, "gen_ai.usage.output_tokens")
    return value if value is not None else _tokens(attributes, "gen_ai.usage.completion_tokens")


def total_tokens(attributes: Mapping[str, Any]) -> int | None:
    value = _tokens(attributes, "gen_ai.usage.total_tokens")
    if value is not None:
        return value
    input_count, output_count = input_tokens(attributes), output_tokens(attributes)
    if input_count is None and output_count is None:
        return None
    return (input_count or 0) + (output_count or 0)


def finish_reason(attributes: Mapping[str, Any]) -> str | None:
    key = "gen_ai.response.finish_reasons"
    if key not in attributes:
        return _string(attributes, "gen_ai.response.finish_reason")
    value = attributes[key]
    if isinstance(value, list | tuple):
        return value[0] if value and isinstance(value[0], str) else None
    return value if isinstance(value, str) else None


def journal_finish_reason(attributes: Mapping[str, Any]) -> str | None:
    value = finish_reason(attributes)
    return value.strip().lower() or None if value is not None else None


def tool_name(attributes: Mapping[str, Any], name: str) -> str | None:
    value = (
        _string(attributes, "gen_ai.tool.name")
        or _string(attributes, "spring.ai.tool.definition.name")
        or _string(attributes, "spring.ai.tool.name")
    )
    if value is not None:
        return value
    return name.partition(" ")[2].strip() or None


def vector_collection(attributes: Mapping[str, Any]) -> str | None:
    return (
        _string(attributes, "db.collection.name")
        or _string(attributes, "spring.ai.vectorstore.collection.name")
        or _string(attributes, "db.namespace")
    )


def vector_operation(attributes: Mapping[str, Any]) -> str | None:
    return (
        _string(attributes, "db.operation.name")
        or _string(attributes, "spring.ai.vectorstore.operation")
        or _string(attributes, "gen_ai.operation.name")
    )
