"""Per-test budget overrides from @pytest.mark.sharpit."""

from __future__ import annotations

from typing import Any

import pytest

from sharpit.engine.testsession.gates import Budget


def budget_for(item: Any, default_max_queries: int | None) -> Budget:
    settings: dict[str, Any] = {"max_queries": default_max_queries, "allow_n_plus_one": False, "max_exceptions": 0}
    for node in item.listchain():
        for mark in node.own_markers:
            if mark.name != "sharpit":
                continue
            unknown = mark.kwargs.keys() - settings.keys()
            if unknown:
                key = min(unknown)
                raise pytest.UsageError(f"sharpit marker: unknown argument '{key}'")
            settings.update(mark.kwargs)
    queries = settings["max_queries"]
    exceptions = settings["max_exceptions"]
    if queries is not None and (not isinstance(queries, int) or queries < 0):
        raise pytest.UsageError("sharpit marker: max_queries must be a non-negative integer")
    if not isinstance(exceptions, int) or exceptions < 0:
        raise pytest.UsageError("sharpit marker: max_exceptions must be a non-negative integer")
    return Budget(queries, bool(settings["allow_n_plus_one"]), exceptions)
