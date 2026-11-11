"""The SARIF 2.1.0 writer (W9 task 3): schema-valid, masked, root-relative URIs, baseline as suppressions."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft4Validator

from engine.testsession.tsfakes import busy_part, render_parts
from sharpit.engine.testsession.sarif import FINGERPRINT_KEY, artifact_uri, to_sarif, write_sarif
from sharpit.engine.testsession.sink import report_masker
from test_masking_corpus import AWS_KEY, GITHUB_TOKEN

SCHEMA = Path(__file__).resolve().parents[2] / "fixtures" / "sarif" / "sarif-schema-2.1.0.json"


@cache
def _validator() -> Draft4Validator:
    return Draft4Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))


def _errors(document: dict[str, Any]) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in _validator().iter_errors(document)]


def _finding(**overrides: Any) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "ruleId": "sharpit.n-plus-one",
        "advisor": "test-runtime",
        "severity": "HIGH",
        "target": "GET /pets",
        "message": "5 identical SELECTs",
        "fingerprint": "test-runtime:sharpit.n-plus-one:0123456789abcdef",
        "testNodeId": "tests/test_pets.py::test_list",
        "dismissed": False,
        "observed": 5,
        "baselineState": None,
    }
    return finding | overrides


def _data(*findings: dict[str, Any]) -> dict[str, Any]:
    return {"tool": {"name": "sharpit", "version": "0.6.0"}, "findings": list(findings)}


def _results(*findings: dict[str, Any]) -> list[dict[str, Any]]:
    return to_sarif(_data(*findings), report_masker())["runs"][0]["results"]


def test_vendored_schema_is_the_official_sarif_2_1_0_schema() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft4Validator.check_schema(schema)
    assert schema["id"] == "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json"


def test_rendered_report_converts_to_a_schema_valid_sarif_log() -> None:
    data = render_parts(busy_part())
    assert data["findings"], "the fixture must carry findings"

    document = to_sarif(data, report_masker())

    assert _errors(document) == []
    assert document["version"] == "2.1.0"
    assert len(document["runs"][0]["results"]) == len(data["findings"])


def test_every_shape_of_finding_is_schema_valid() -> None:
    findings = [
        _finding(),
        _finding(severity="INFO", baselineState="existing"),
        _finding(dismissed=True, testNodeId=None),
        _finding(location={"path": "src/app.py", "line": 12}),
        _finding(location={"path": "/etc/passwd"}),
    ]

    assert _errors(to_sarif(_data(*findings), report_masker())) == []


def test_driver_names_sharpit_and_lists_each_rule_once() -> None:
    document = to_sarif(_data(_finding(), _finding(ruleId="rest.unauthenticated")), report_masker())

    driver = document["runs"][0]["tool"]["driver"]
    assert driver["name"] == "sharpit"
    assert driver["version"] == "0.6.0"
    assert [rule["id"] for rule in driver["rules"]] == ["rest.unauthenticated", "sharpit.n-plus-one"]


@pytest.mark.parametrize(
    ("severity", "level"),
    [("CRITICAL", "error"), ("HIGH", "error"), ("MEDIUM", "warning"), ("LOW", "note"), ("INFO", "note")],
)
def test_level_follows_severity(severity: str, level: str) -> None:
    (result,) = _results(_finding(severity=severity))

    assert result["level"] == level


def test_result_carries_rule_id_and_the_versioned_location_free_fingerprint() -> None:
    (result,) = _results(_finding())

    assert result["ruleId"] == "sharpit.n-plus-one"
    assert result["partialFingerprints"] == {FINGERPRINT_KEY: "test-runtime:sharpit.n-plus-one:0123456789abcdef"}
    assert FINGERPRINT_KEY.endswith("/v1")


def test_baselined_finding_is_suppressed() -> None:
    (result,) = _results(_finding(baselineState="existing"))

    assert [s["kind"] for s in result.get("suppressions", [])] == ["external"]


def test_dismissed_finding_is_suppressed() -> None:
    (result,) = _results(_finding(dismissed=True))

    assert [s["kind"] for s in result.get("suppressions", [])] == ["external"]


@pytest.mark.parametrize("state", [None, "new"])
def test_new_or_unbaselined_finding_is_not_suppressed(state: str | None) -> None:
    (result,) = _results(_finding(baselineState=state))

    assert "suppressions" not in result


def test_location_less_finding_keeps_its_target_as_a_logical_location() -> None:
    (result,) = _results(_finding())

    (location,) = result["locations"]
    assert "physicalLocation" not in location
    assert location.get("logicalLocations") == [{"fullyQualifiedName": "GET /pets"}]


def test_location_is_root_relative() -> None:
    (result,) = _results(_finding(location={"path": "src/app/main.py", "line": 7}))

    physical = result["locations"][0].get("physicalLocation", {})
    assert physical.get("artifactLocation") == {"uri": "src/app/main.py", "uriBaseId": "%SRCROOT%"}
    assert physical.get("region") == {"startLine": 7}


@pytest.mark.parametrize(
    ("path", "uri"),
    [
        ("src/app.py", "src/app.py"),
        ("src\\app\\main.py", "src/app/main.py"),  # Windows separators become POSIX
        ("./src/app.py", "src/app.py"),
        ("src/my file#1.py", "src/my%20file%231.py"),
        ("src/caf\u00e9.py", "src/caf%C3%A9.py"),
    ],
)
def test_artifact_uri_is_posix_and_percent_encoded(path: str, uri: str) -> None:
    assert artifact_uri(path) == uri


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/etc/passwd",
        "../secrets.py",
        "src/../../escape.py",
        "src\\..\\..\\escape.py",
        "C:\\Users\\dev\\app.py",
        "C:app.py",
        "c:/app.py",
        "\\\\server\\share\\app.py",
        "file:///etc/passwd",
        "https://example.com/app.py",
    ],
)
def test_artifact_uri_rejects_paths_outside_the_root(path: str) -> None:
    assert artifact_uri(path) is None


def test_escaping_location_is_dropped_but_the_finding_kept() -> None:
    (result,) = _results(_finding(location={"path": "../outside.py", "line": 3}))

    (location,) = result["locations"]
    assert "physicalLocation" not in location
    assert result["ruleId"] == "sharpit.n-plus-one"


def test_masked_path_drops_the_physical_location() -> None:
    # a masked path names no real file: the finding keeps only its logical location
    (result,) = _results(_finding(location={"path": f"src/{AWS_KEY}.py", "line": 1}))

    (location,) = result["locations"]
    assert "physicalLocation" not in location
    assert location.get("logicalLocations") == [{"fullyQualifiedName": "GET /pets"}]


def test_planted_secrets_never_reach_the_sarif_file(tmp_path: Path) -> None:
    planted = _finding(
        message=f"token {GITHUB_TOKEN} leaked",
        target=f"GET /keys?k={AWS_KEY}",
        testNodeId=f"tests/test_a.py::test_x[{GITHUB_TOKEN}]",
        location={"path": f"src/{AWS_KEY}.py", "line": 1},
    )
    target = tmp_path / "out" / "sharpit.sarif"

    write_sarif(target, _data(planted), report_masker())

    text = target.read_text(encoding="utf-8")
    assert GITHUB_TOKEN not in text
    assert AWS_KEY not in text
    assert "leaked" in text


def test_write_sarif_writes_valid_json(tmp_path: Path) -> None:
    target = tmp_path / "sharpit.sarif"

    write_sarif(target, _data(_finding()), report_masker())

    assert _errors(json.loads(target.read_text(encoding="utf-8"))) == []
