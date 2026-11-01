from __future__ import annotations

import json
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


def test_conftest_crash_still_restores(pytester: pytest.Pytester) -> None:
    original_connect = sqlite3.connect
    pytester.makeconftest("raise RuntimeError('conftest import failed')")
    pytester.makepyfile("def test_never_runs(): pass")

    pytester.runpytest_inprocess("--sharpit", "-q")

    assert sqlite3.connect is original_connect


def test_xdist_report_written_once_by_controller(pytester: pytest.Pytester) -> None:
    original_connect = sqlite3.connect
    pytester.makepyfile(
        """
        import sqlite3
        def test_left(): sqlite3.connect(':memory:').execute('SELECT 1')
        def test_right(): sqlite3.connect(':memory:').execute('SELECT 2')
        """
    )

    result = pytester.runpytest(
        "-n", "2", "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert len(data["workers"]) == 2
    assert len(data["tests"]) == 2
    assert sqlite3.connect is original_connect


def test_reports_written_and_valid(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_empty(): pass")

    result = pytester.runpytest(
        "--sharpit", "--sharpit-allow-unknown", "--sharpit-report=report.json", "--sharpit-junit=report.xml", "-q"
    )

    assert result.ret == 0
    import jsonschema

    data = json.loads((pytester.path / "report.json").read_text())
    schema_path = Path(__file__).resolve().parents[2] / "src/sharpit/engine/testsession/report.schema.json"
    jsonschema.validate(data, json.loads(schema_path.read_text()))
    assert data["schema"] == "sharpit-report/1"
    assert (pytester.path / "report.xml").exists()
    ET.parse(pytester.path / "report.xml")
