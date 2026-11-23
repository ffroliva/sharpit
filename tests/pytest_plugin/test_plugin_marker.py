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

    item = Item()
    with pytest.raises(pytest.UsageError, match="sharpit marker: unknown argument 'mystery'"):
        budget_for(item, None)


def test_marker_accept_requires_reason_when_configured() -> None:
    from sharpit.pytest_plugin.marker import budget_for

    class Marker:
        name = "sharpit"
        kwargs = {"allow_swallowed": True}

    class Item:
        own_markers = [Marker()]
        nodeid = "tests/test_x.py::test_case"

        def listchain(self) -> list[object]:
            return [self]

    item = Item()
    with pytest.raises(pytest.UsageError) as exc_info:
        budget_for(item, None, require_reason=True)

    err = str(exc_info.value)
    assert "tests/test_x.py::test_case" in err
    assert "@pytest.mark.sharpit" in err


def test_marker_accept_with_reason_passes_when_configured() -> None:
    from sharpit.pytest_plugin.marker import budget_for

    class Marker:
        name = "sharpit"
        kwargs = {"allow_swallowed": True, "reason": "documented reason"}

    class Item:
        own_markers = [Marker()]
        nodeid = "tests/test_x.py::test_case"

        def listchain(self) -> list[object]:
            return [self]

    budget = budget_for(Item(), None, require_reason=True)
    assert budget.allow_swallowed is True
    assert budget.reason == "documented reason"
