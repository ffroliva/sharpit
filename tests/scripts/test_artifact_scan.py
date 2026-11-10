"""Tests for scripts/ci/artifact_scan.py (W0b Task 5).

Verifies that no uploaded artifact carries a planted canary value in any form
(raw, URL-encoded, JSON-escaped, base64), that the value itself is never printed,
and that --require enforces values presence.
"""

from __future__ import annotations

import base64
import json
import urllib.parse
from pathlib import Path

import pytest
from _load import load_script

scanner = load_script("scripts/ci/artifact_scan.py")


def test_the_artifact_scan_finds_every_form_of_a_value(tmp_path: Path) -> None:
    # Runtime-built canary token: contains special chars so each form is unique
    token = "".join(["canary", "-", "token", " ", "v1", "/", "x", "'", '"'])
    raw_val = token
    url_val = urllib.parse.quote(token)
    json_val = json.dumps(token)[1:-1]
    b64_val = base64.b64encode(token.encode("utf-8")).decode("ascii")

    # Assert the four forms are pairwise distinct strings
    assert len({raw_val, url_val, json_val, b64_val}) == 4

    # Plant raw and url forms in a JUnit XML
    junit_path = tmp_path / "junit.xml"
    junit_path.write_text(
        f"""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="canary-suite" errors="0" failures="1" skipped="0" tests="2">
    <testcase classname="test_canary" name="test_raw">
      <failure message="leaked raw: {raw_val}">traceback</failure>
    </testcase>
    <testcase classname="test_canary" name="test_url">
      <system-out>leaked url: {url_val}</system-out>
    </testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )

    # Plant json-escaped and base64 forms in a JSONL file
    jsonl_path = tmp_path / "overhead.jsonl"
    jsonl_path.write_text(
        json.dumps({"event": "query", "sql": f"SELECT '{json_val}'"})
        + "\n"
        + json.dumps({"event": "auth", "token": b64_val})
        + "\n",
        encoding="utf-8",
    )

    hits = scanner.scan([junit_path, jsonl_path], [token])

    # Must find all 4 forms
    forms = {h.form for h in hits}
    assert forms == {"raw", "URL-encoded", "JSON-escaped", "base64"}

    # File associations
    junit_hits = [h for h in hits if h.path == junit_path]
    jsonl_hits = [h for h in hits if h.path == jsonl_path]
    assert {h.form for h in junit_hits} == {"raw", "URL-encoded"}
    assert {h.form for h in jsonl_hits} == {"JSON-escaped", "base64"}

    # Each hit names a positive line number and value_index 0
    for h in hits:
        assert h.line > 0
        assert h.value_index == 0


def test_the_artifact_scan_never_prints_the_value(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    token = "".join(["sharpit", "_", "canary", "_", "secret", "_", "42"])
    target_file = tmp_path / "target.xml"
    target_file.write_text(f"<testsuite><failure>{token}</failure></testsuite>\n", encoding="utf-8")

    values_file = tmp_path / "values.txt"
    values_file.write_text(f"{token}\n", encoding="utf-8")

    rc = scanner.main(["--values-file", str(values_file), str(target_file)])
    assert rc == 1, "scanner must fail on planted value hit"

    captured = capsys.readouterr()
    combined_output = captured.out + captured.err

    # The planted value itself must NEVER appear in output
    assert token not in combined_output

    # The location (file, line), form, and value index must appear
    assert "target.xml" in combined_output
    assert "raw" in combined_output
    assert "value_index=0" in combined_output or "value #0" in combined_output or "#0" in combined_output


def test_require_fails_without_values(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    nonexistent = tmp_path / "does_not_exist.txt"
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    target = tmp_path / "artifact.xml"
    target.write_text("<testsuite/>\n", encoding="utf-8")

    # With --require: missing file fails
    rc_missing = scanner.main(["--require", "--values-file", str(nonexistent), str(target)])
    assert rc_missing != 0

    # With --require: empty file fails
    rc_empty = scanner.main(["--require", "--values-file", str(empty), str(target)])
    assert rc_empty != 0

    # Without --require: missing file passes and prints "no planted values in this job"
    rc_pass = scanner.main(["--values-file", str(nonexistent), str(target)])
    assert rc_pass == 0
    captured = capsys.readouterr()
    assert "no planted values in this job" in captured.out
