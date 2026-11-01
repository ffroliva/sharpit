from __future__ import annotations

import pytest


def test_marker_budget_uses_nearest_mark() -> None:
    from sharpit.pytest_plugin.marker import budget_for

    class Marker:
        name = "sharpit"

        def __init__(self, kwargs):
            self.kwargs = kwargs

    class Item:
        own_markers = [Marker({"max_queries": 5}), Marker({"max_queries": 2, "allow_n_plus_one": True})]

        def listchain(self):
            return [self]

    budget = budget_for(Item(), 10)

    assert budget.max_queries == 2
    assert budget.allow_n_plus_one is True


def test_marker_unknown_argument_is_usage_error() -> None:
    from sharpit.pytest_plugin.marker import budget_for

    class Marker:
        name = "sharpit"
        kwargs = {"mystery": True}

    class Item:
        own_markers = [Marker()]

        def listchain(self):
            return [self]

    with pytest.raises(pytest.UsageError, match="sharpit marker: unknown argument 'mystery'"):
        budget_for(Item(), None)
