"""Per-test budget overrides from @pytest.mark.sharpit."""

from __future__ import annotations

from typing import Any

import pytest

from sharpit.engine.testsession.gates import Budget


def _marker_settings(item: Any, default_max_queries: int | None) -> dict[str, Any]:
    """The defaults overlaid by every ``sharpit`` marker on the item's chain, outermost first."""
    settings: dict[str, Any] = {
        "max_queries": default_max_queries,
        "allow_n_plus_one": False,
        "max_exceptions": 0,
        "allow_swallowed": False,
        "allow_unbounded_read": False,
        "reason": None,
    }
    for node in item.listchain():
        for mark in node.own_markers:
            if mark.name != "sharpit":
                continue
            unknown = mark.kwargs.keys() - settings.keys()
            if unknown:
                key = min(unknown)
                raise pytest.UsageError(f"sharpit marker: unknown argument '{key}'")
            settings.update(mark.kwargs)
    return settings


def budget_for(
    item: Any,
    default_max_queries: int | None,
    *,
    unbounded_read_factor: int = 2,
    require_reason: bool = False,
) -> Budget:
    settings = _marker_settings(item, default_max_queries)
    queries = settings["max_queries"]
    exceptions = settings["max_exceptions"]
    reason = settings["reason"]
    if queries is not None and (not isinstance(queries, int) or queries < 0):
        raise pytest.UsageError("sharpit marker: max_queries must be a non-negative integer")
    if not isinstance(exceptions, int) or exceptions < 0:
        raise pytest.UsageError("sharpit marker: max_exceptions must be a non-negative integer")
    if reason is not None and not isinstance(reason, str):
        raise pytest.UsageError("sharpit marker: reason must be a string")
    reason_str = reason.strip() if isinstance(reason, str) and reason.strip() else None
    if (
        require_reason
        and not reason_str
        and (settings["allow_swallowed"] or settings["allow_n_plus_one"] or settings["allow_unbounded_read"])
    ):
        node_id = getattr(item, "nodeid", getattr(item, "name", str(item)))
        raise pytest.UsageError(f"{node_id}: @pytest.mark.sharpit requires a reason for accepted findings")
    return Budget(
        queries,
        bool(settings["allow_n_plus_one"]),
        exceptions,
        bool(settings["allow_swallowed"]),
        bool(settings["allow_unbounded_read"]),
        unbounded_read_factor,
        reason=reason_str,
    )
