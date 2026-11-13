"""Golden loader shape rules (ruling after the G0a review): a golden list keeps one item per distinct shape."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import golden
from golden import assert_parity


@pytest.fixture
def capture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(golden, "ROOT", tmp_path)

    def write(data: object) -> None:
        (tmp_path / "2.2.0" / "data").mkdir(parents=True, exist_ok=True)
        (tmp_path / "2.2.0" / "data" / "captured.json").write_text(json.dumps(data), encoding="utf-8")

    return write


def _error(payload: dict[str, Any]) -> str | None:
    try:
        assert_parity("data", "data", payload)
    except AssertionError as exc:
        return str(exc)
    return None


def test_payload_item_matches_any_golden_shape(capture) -> None:
    capture({"items": [{"kind": "a", "x": 1}, {"kind": "b", "y": "s"}]})
    assert _error({"items": [{"kind": "b", "y": "t"}, {"kind": "a", "x": 2}]}) is None


def test_payload_item_matching_no_golden_shape_is_rejected(capture) -> None:
    capture({"items": [{"kind": "a", "x": 1}, {"kind": "b", "y": "s"}]})
    error = _error({"items": [{"kind": "c"}]})
    assert error is not None
    assert "items[]" in error


def test_null_allowed_where_any_golden_item_is_null(capture) -> None:
    capture({"items": [{"v": 1, "w": 2}, {"v": None, "z": "q"}]})
    assert _error({"items": [{"v": None, "w": 3}]}) is None


def test_any_golden_type_at_a_path_is_accepted(capture) -> None:
    capture({"items": [{"v": 1, "w": 2}, {"v": "s", "z": "q"}]})
    assert _error({"items": [{"v": "t", "w": 3}]}) is None


def test_a_type_no_golden_item_has_is_rejected(capture) -> None:
    capture({"items": [{"v": 1, "w": 2}, {"v": "s", "z": "q"}]})
    error = _error({"items": [{"v": True, "w": 3}]})
    assert error is not None
    assert "items[].v" in error
