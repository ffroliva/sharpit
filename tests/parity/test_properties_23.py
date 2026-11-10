"""Sharpit settings parity against the BootUI 2.3.0 property fixture."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine.masking import Exposure
from sharpit.settings import load_settings
from sharpit.settings_registry import SPECS, UNSET

_SOURCE_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "bootui" / "2.3.0" / "properties.json"
_FIXTURE = Path(os.environ.get("SHARPIT_PROPERTIES_FIXTURE", _SOURCE_FIXTURE))
_ROWS = Path(__file__).resolve().parents[2].parent / "briefs-0.6.0" / "W3-A1-rows.txt"


def _field(key: str) -> str:
    return re.sub(r"[.-]", "_", key.removeprefix("bootui."))


def _expected_default(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, str) and re.fullmatch(r"\d+(?:\.\d+)?(?:ms|s)?", value):
        number, unit = re.fullmatch(r"(\d+(?:\.\d+)?)(ms|s)?", value).groups()  # type: ignore[union-attr]
        return float(number) / 1000 if unit == "ms" else float(number)
    if value in {"auto", "off", "on"}:
        return value.upper()
    if isinstance(value, str) and value in {"masked", "metadata_only", "full"}:
        return Exposure(value.upper())
    return value


def _samples(default: Any, field: str) -> tuple[str, str | None] | None:
    if isinstance(default, bool):
        return ("false" if default else "true"), "invalid-bool"
    if isinstance(default, int):
        return str(default + 1), "invalid-int"
    if isinstance(default, float):
        return f"{default + 1}s", "invalid-duration"
    if isinstance(default, tuple) or field == "authentication_token":
        return "parity-item", None
    if field in {"enabled", "trust_container_gateway", "mcp_enabled"}:
        return "ON", "invalid-mode"
    if field == "expose_values":
        return "FULL", "invalid-exposure"
    if field in {"vulnerabilities_osv_base_uri", "vulnerabilities_epss_base_uri"}:
        return "https://parity.test", "file:///invalid"
    return None


def _cases() -> list[tuple[str, str, Any, Any]]:
    fixture = json.loads(_SOURCE_FIXTURE.read_text(encoding="utf-8"))
    properties = {item["name"]: item for item in fixture["properties"]}
    settings = load_settings({}, {})
    rows = [line.strip()[5:] for line in _ROWS.read_text(encoding="utf-8").splitlines()]
    cases = []
    for key in rows:
        item = properties.get(key)
        field = _field(key)
        if item is None or field not in SPECS or field not in vars(settings):
            continue
        default = _expected_default(item.get("defaultValue"))
        if getattr(settings, field) != default:
            continue
        env = "SHARPIT_" + re.sub(r"[.-]", "_", key.removeprefix("bootui.")).upper()
        samples = _samples(default, field)
        if samples is None:
            continue
        valid, invalid = samples
        failsafe = SPECS[field][1]
        expected_failsafe = getattr(settings, field) if failsafe is None else None if failsafe is UNSET else failsafe
        if field == "enabled":
            expected_failsafe = "invalid-mode"
        if invalid is None:
            cases.append((key, field, (env, valid), None))
            continue
        cases.append((key, field, (env, valid), (env, invalid, expected_failsafe)))
    return cases


_CASES = _cases()


@pytest.mark.parametrize("key,field,valid,invalid", _CASES, ids=[f"prop:{case[0]}" for case in _CASES])
def test_property_matches_bootui_23_fixture(
    key: str, field: str, valid: tuple[str, str], invalid: tuple[str, str, Any] | None
):
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    entry = next(item for item in fixture["properties"] if item["name"] == key)
    default = _expected_default(entry.get("defaultValue"))
    settings = load_settings({}, {})
    assert getattr(settings, field) == default

    env, raw = valid
    loaded = load_settings({}, {env: raw})
    assert getattr(loaded, field) != default

    if invalid is None:
        return
    env, raw, failsafe = invalid
    rejected = load_settings({}, {env: raw})
    assert getattr(rejected, field) == failsafe
    assert f"Ignoring invalid {env} value" in " ".join(rejected.warnings)
