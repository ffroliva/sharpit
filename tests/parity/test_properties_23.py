"""Sharpit settings parity against the BootUI 2.3.0 property fixture."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine.masking import Exposure
from sharpit.settings import load_settings
from sharpit.settings_registry import SPECS, UNSET

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "bootui" / "2.3.0" / "properties.json"
_STATUS = Path(__file__).with_name("properties_23_status.json")

pytestmark = [
    pytest.mark.bootui("prop:bootui.activity.max-entries"),
    pytest.mark.bootui("prop:bootui.activity.n-plus-one-threshold"),
    pytest.mark.bootui("prop:bootui.activity.request-slow-threshold-ms"),
    pytest.mark.bootui("prop:bootui.advisors.max-retained-violations"),
    pytest.mark.bootui("prop:bootui.allow-non-localhost"),
    pytest.mark.bootui("prop:bootui.allowed-hosts"),
    pytest.mark.bootui("prop:bootui.authentication.token"),
    pytest.mark.bootui("prop:bootui.cli.enabled"),
    pytest.mark.bootui("prop:bootui.cli.execution-timeout"),
    pytest.mark.bootui("prop:bootui.cli.max-concurrent-calls"),
    pytest.mark.bootui("prop:bootui.cli.max-results"),
    pytest.mark.bootui("prop:bootui.disabled-profiles"),
    pytest.mark.bootui("prop:bootui.enabled"),
    pytest.mark.bootui("prop:bootui.exceptions.max-groups"),
    pytest.mark.bootui("prop:bootui.exceptions.max-occurrences-per-group"),
    pytest.mark.bootui("prop:bootui.exceptions.max-stack-frames"),
    pytest.mark.bootui("prop:bootui.expose-values"),
    pytest.mark.bootui("prop:bootui.http-exchanges.max-exchanges"),
    pytest.mark.bootui("prop:bootui.mask-secrets"),
    pytest.mark.bootui("prop:bootui.mcp.enabled"),
    pytest.mark.bootui("prop:bootui.mcp.execution-timeout"),
    pytest.mark.bootui("prop:bootui.mcp.max-concurrent-calls"),
    pytest.mark.bootui("prop:bootui.mcp.max-payload-bytes"),
    pytest.mark.bootui("prop:bootui.mcp.max-response-bytes"),
    pytest.mark.bootui("prop:bootui.mcp.max-results"),
    pytest.mark.bootui("prop:bootui.mysql.max-indexes"),
    pytest.mark.bootui("prop:bootui.mysql.max-lock-waits"),
    pytest.mark.bootui("prop:bootui.mysql.max-replication-channels"),
    pytest.mark.bootui("prop:bootui.mysql.max-sessions"),
    pytest.mark.bootui("prop:bootui.mysql.max-settings"),
    pytest.mark.bootui("prop:bootui.mysql.max-statements"),
    pytest.mark.bootui("prop:bootui.mysql.max-tables"),
    pytest.mark.bootui("prop:bootui.postgresql.max-indexes"),
    pytest.mark.bootui("prop:bootui.postgresql.max-replicas"),
    pytest.mark.bootui("prop:bootui.postgresql.max-sessions"),
    pytest.mark.bootui("prop:bootui.postgresql.max-settings"),
    pytest.mark.bootui("prop:bootui.postgresql.max-statements"),
    pytest.mark.bootui("prop:bootui.postgresql.max-tables"),
    pytest.mark.bootui("prop:bootui.postgresql.max-vacuum-tables"),
    pytest.mark.bootui("prop:bootui.read-only"),
    pytest.mark.bootui("prop:bootui.runtime-journal.enabled"),
    pytest.mark.bootui("prop:bootui.runtime-journal.max-events"),
    pytest.mark.bootui("prop:bootui.runtime-journal.queue-capacity"),
    pytest.mark.bootui("prop:bootui.security-logs.max-logs"),
    pytest.mark.bootui("prop:bootui.show-banner"),
    pytest.mark.bootui("prop:bootui.sql-trace.capture-call-site"),
    pytest.mark.bootui("prop:bootui.sql-trace.capture-parameters"),
    pytest.mark.bootui("prop:bootui.sql-trace.enabled"),
    pytest.mark.bootui("prop:bootui.sql-trace.max-entries"),
    pytest.mark.bootui("prop:bootui.sql-trace.max-parameter-length"),
    pytest.mark.bootui("prop:bootui.sql-trace.max-sql-length"),
    pytest.mark.bootui("prop:bootui.sql-trace.n-plus-one-threshold"),
    pytest.mark.bootui("prop:bootui.sql-trace.recording"),
    pytest.mark.bootui("prop:bootui.sql-trace.slow-query-threshold-millis"),
    pytest.mark.bootui("prop:bootui.transactions.connection-hold-threshold-millis"),
    pytest.mark.bootui("prop:bootui.transactions.enabled"),
    pytest.mark.bootui("prop:bootui.transactions.max-entries"),
    pytest.mark.bootui("prop:bootui.transactions.recording"),
    pytest.mark.bootui("prop:bootui.transactions.slow-transaction-threshold-millis"),
    pytest.mark.bootui("prop:bootui.trust-container-gateway"),
    pytest.mark.bootui("prop:bootui.trusted-proxies"),
    pytest.mark.bootui("prop:bootui.vulnerabilities.epss-base-uri"),
    pytest.mark.bootui("prop:bootui.vulnerabilities.epss-enabled"),
    pytest.mark.bootui("prop:bootui.vulnerabilities.max-advisories"),
    pytest.mark.bootui("prop:bootui.vulnerabilities.max-packages"),
    pytest.mark.bootui("prop:bootui.vulnerabilities.osv-base-uri"),
    pytest.mark.bootui("prop:bootui.vulnerabilities.osv-enabled"),
    pytest.mark.bootui("prop:bootui.vulnerabilities.request-timeout"),
]


def test_bootui_marks_equal_the_matched_rows() -> None:
    source = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    assignment = next(
        (
            node
            for node in source.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets)
        ),
        None,
    )
    marked = {
        call.args[0].value
        for call in ast.walk(assignment.value if assignment is not None else ast.List(elts=[], ctx=ast.Load()))
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "bootui"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    }
    _, status = _fixture_and_status()
    matched = {"prop:" + row["name"] for row in status["properties"] if row["status"] == "matched"}
    assert marked == matched


def _field(key: str) -> str:
    return re.sub(r"[.-]", "_", key.removeprefix("bootui."))


def _expected_default(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, str) and (match := re.fullmatch(r"(\d+(?:\.\d+)?)(ms|s)?", value)):
        return float(match.group(1)) / 1000 if match.group(2) == "ms" else float(match.group(1))
    if isinstance(value, str) and value in {"auto", "off", "on"}:
        return value.upper()
    if isinstance(value, str) and value in {"masked", "metadata_only", "full"}:
        return Exposure(value.upper())
    return value


def _samples(default: Any, field: str) -> tuple[str, Any, str | None] | None:
    if isinstance(default, bool):
        return ("false" if default else "true"), not default, "invalid-bool"
    if isinstance(default, int):
        return str(default + 1), default + 1, "invalid-int"
    if isinstance(default, float):
        return f"{default + 1}s", default + 1, "invalid-duration"
    if isinstance(default, tuple) or field == "authentication_token":
        return "parity-item", ("parity-item",) if isinstance(default, tuple) else "parity-item", None
    if field in {"enabled", "trust_container_gateway", "mcp_enabled"}:
        return "ON", "ON", "invalid-mode"
    if field == "expose_values":
        return "FULL", Exposure.FULL, "invalid-exposure"
    if field in {"vulnerabilities_osv_base_uri", "vulnerabilities_epss_base_uri"}:
        return "https://parity.test", "https://parity.test", "file:///invalid"
    return None


def _fixture_and_status() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return (
        json.loads(_FIXTURE.read_text(encoding="utf-8"))["properties"],
        json.loads(_STATUS.read_text(encoding="utf-8")),
    )


def _classification(item: dict[str, Any], settings: Any) -> tuple[str, str | None]:
    key = item["name"]
    field = _field(key)
    expected = _expected_default(item.get("defaultValue"))
    if field in {"path", "api_path"}:
        actual = getattr(settings, field)
    elif field not in SPECS or field not in vars(settings):
        return "missing", f"No sharpit setting field/parser for {field}"
    else:
        actual = getattr(settings, field)
    if actual != expected:
        return "partial", f"default differs: BootUI={expected!r}; sharpit={actual!r}"
    if _samples(expected, field) is None:
        return "partial", "No valid environment sample is defined"
    return "matched", None


def test_fixture_properties_are_fully_classified() -> None:
    fixture, status = _fixture_and_status()
    properties = status["properties"]
    names = [item["name"] for item in fixture]
    assert [row["name"] for row in properties] == names
    classified = {row["name"] for row in properties if row["status"] in {"matched", "partial", "missing"}}
    assert classified == set(names)
    settings = load_settings({}, {})
    for item, row in zip(fixture, properties, strict=True):
        actual_status, difference = _classification(item, settings)
        assert row["status"] == actual_status
        assert row["difference"] == difference
    assert status["panel_map_rule"] == (
        "bootui.panels is the sole fixture entry for panel configuration; bootui.panels.* keys are map members, "
        "not property rows, and are not synthesized from the settings registry."
    )
    panels = next(item for item in fixture if item["name"] == "bootui.panels")
    assert panels["defaultValue"] is None
    assert not any(name.startswith("bootui.panels.") for name in names)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("auto", "AUTO"), ("off", "OFF"), ("on", "ON"), ("31s", 31.0), ("250ms", 0.25), (["a", "b"], ("a", "b"))],
)
def test_expected_default_conversions(value: Any, expected: Any) -> None:
    assert _expected_default(value) == expected


def _matched_cases() -> list[tuple[str, str, str, Any, Any, str | None, Any]]:
    fixture, status = _fixture_and_status()
    settings = load_settings({}, {})
    cases = []
    rows = {row["name"]: row for row in status["properties"]}
    for item in fixture:
        row = rows.get(item["name"])
        if row is None or row["status"] != "matched":
            continue
        field = _field(item["name"])
        default = _expected_default(item.get("defaultValue"))
        sample = _samples(default, field)
        assert sample is not None
        raw, expected, invalid = sample
        env = "SHARPIT_" + re.sub(r"[.-]", "_", item["name"].removeprefix("bootui.")).upper()
        failsafe = SPECS[field][1]
        if field == "enabled":
            failsafe = invalid  # settings.py retains the invalid text so activation can report it
        elif failsafe is None:
            failsafe = getattr(settings, field)
        elif failsafe is UNSET:
            failsafe = None
        cases.append((item["name"], field, env, raw, expected, invalid, failsafe))
    return cases


@pytest.mark.parametrize(
    "key,field,env,raw,expected,invalid,failsafe",
    _matched_cases(),
    ids=lambda v: v if isinstance(v, str) and v.startswith("bootui.") else None,
)
def test_matched_property_default_and_values(
    key: str, field: str, env: str, raw: str, expected: Any, invalid: str | None, failsafe: Any
) -> None:
    fixture, _ = _fixture_and_status()
    entry = next(item for item in fixture if item["name"] == key)
    default = _expected_default(entry.get("defaultValue"))
    settings = load_settings({}, {})
    assert getattr(settings, field) == default
    loaded = load_settings({}, {env: raw})
    assert getattr(loaded, field) == expected
    if invalid is None:
        return
    rejected = load_settings({}, {env: invalid})
    assert getattr(rejected, field) == failsafe
    assert f"Ignoring invalid {env} value" in " ".join(rejected.warnings)
