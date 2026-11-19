"""FASTAPI-ERR-001 (new, N): a route handler module with a broad handler that swallows (spec 0.4.0 §5.5 F1)."""

from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

from sharpit.engine.collectors.restapi.rules import FASTAPI_ERR_001, swallowed_handler_violations
from sharpit.engine.spi import ApiRouteInfo


def _module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, source: str) -> None:
    """Register a module object for ``source`` without executing it: the rule must only read the file."""
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(source).lstrip("\n"), "utf-8")
    module = ModuleType(name)
    module.__file__ = str(path)
    monkeypatch.setitem(sys.modules, name, module)


def _route(handler: str) -> ApiRouteInfo:
    return ApiRouteInfo(("GET",), "/weeks/count", handler)


def test_fastapi_err_rule_flags_swallowed_broad_handler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _module(
        tmp_path,
        monkeypatch,
        "swallow_routes_flagged",
        """
        def get_week_count():
            try:
                return len(WEEKS)
            except Exception:
                return 0

        def week_count():
            return {"week_count": get_week_count()}
        """,
    )

    found = swallowed_handler_violations([_route("swallow_routes_flagged:week_count")])

    [violation] = found
    assert re.fullmatch(r"swallow_routes_flagged:get_week_count#[0-9a-f]{8}", violation.target)
    assert FASTAPI_ERR_001.id == "FASTAPI-ERR-001"


def test_fastapi_err_rule_ignores_logged_handler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _module(
        tmp_path,
        monkeypatch,
        "swallow_routes_logged",
        """
        import logging

        logger = logging.getLogger(__name__)

        def week_count():
            try:
                return {"week_count": len(WEEKS)}
            except ValueError:
                return {"week_count": -1}
            except Exception:
                logger.exception("week count failed")
                return {"week_count": 0}
        """,
    )

    assert swallowed_handler_violations([_route("swallow_routes_logged:week_count")]) == []


def test_the_violation_target_keeps_its_identity_when_a_line_is_added_above(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = """
        def get_week_count():
            try:
                return len(WEEKS)
            except Exception:
                return 0

        def week_count():
            return {"week_count": get_week_count()}
        """
    _module(tmp_path, monkeypatch, "swallow_routes_stable", source)
    before = swallowed_handler_violations([_route("swallow_routes_stable:week_count")])
    path = tmp_path / "swallow_routes_stable.py"
    path.write_text("# a line added above\n" + path.read_text("utf-8"), "utf-8")

    after = swallowed_handler_violations([_route("swallow_routes_stable:week_count")])

    assert re.fullmatch(r"swallow_routes_stable:get_week_count#[0-9a-f]{8}", before[0].target)
    assert [v.target for v in after] == [v.target for v in before]
    assert [v.message for v in after] != [v.message for v in before]
