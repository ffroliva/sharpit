"""REST API error-contract declarations."""

from typing import Any

from sharpit.engine.spi import ApiModel


def error_contract_report(
    model: ApiModel, index: object | None, q: str | None, offset: int, limit: int | None
) -> dict[str, Any]:
    del model, index, q, offset, limit
    return {
        "available": False,
        "unavailableReason": (
            "Not available: this stack has no error-contract backend wired, so declared exception handlers "
            "cannot be catalogued."
        ),
        "total": 0,
        "handlerCount": 0,
        "componentCount": 0,
        "exceptionTypeCount": 0,
        "truncated": False,
        "maxEntries": 500,
        "entries": [],
        "page": {"total": 0, "matched": 0, "offset": 0, "limit": 0, "returned": 0, "hasMore": False},
    }


def entries(model: ApiModel, index: object | None) -> list[Any]:
    del model, index
    return []
