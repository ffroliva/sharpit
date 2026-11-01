"""The published ``sharpit-report/1`` schema (0.3.0 spec §7.1): it validates what ``render`` emits and ships twice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

import sharpit.engine.testsession as testsession_pkg
from engine.testsession.tsfakes import busy_part, part, render_parts

PACKAGED = Path(testsession_pkg.__file__).parent / "report.schema.json"
PUBLISHED = Path(__file__).resolve().parents[1] / "docs" / "reference" / "report.schema.json"


def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(PACKAGED.read_text(encoding="utf-8")))


def _errors(data: dict[str, Any]) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in _validator().iter_errors(data)]


def test_schema_is_a_valid_2020_12_schema() -> None:
    Draft202012Validator.check_schema(json.loads(PACKAGED.read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    ("name", "build"),
    [
        ("fail", lambda: render_parts(busy_part())),
        ("unknown", lambda: render_parts(part(sources=[]), missing=("gw1",))),
        ("pass", lambda: render_parts(part())),
    ],
)
def test_schema_validates_render(name: str, build: Any) -> None:
    data = build()
    assert data["status"] == name
    assert _errors(data) == []


def test_schema_rejects_a_missing_key_and_a_wrong_type() -> None:
    data = render_parts(part())
    del data["totals"]
    data["generatedAt"] = "yesterday"
    assert len(_errors(data)) == 2


def test_schema_lets_consumers_ignore_new_keys() -> None:
    data = render_parts(busy_part())
    data["futureKey"] = {"anything": 1}
    data["tests"][0]["futureKey"] = 1
    assert _errors(data) == []


def test_schema_copies_identical() -> None:
    """The wheel's copy and the documented copy are the same bytes."""
    assert PACKAGED.read_bytes() == PUBLISHED.read_bytes()
