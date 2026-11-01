from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest


def _run_report_corpus(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    variable: str | None,
    value: str | None,
    warning: str | None,
) -> None:
    secret = "sk_live_12345678901234567890"
    pytester.makepyfile(
        appmod=f"""
        from fastapi import FastAPI
        app = FastAPI()
        @app.get('/{secret}')
        def endpoint(): return 1
        """
    )
    pytester.makepyfile(
        f"""
        import logging
        import sqlite3
        import pytest
        @pytest.fixture(autouse=True)
        def exception_during_setup():
            try: raise ValueError('{secret}')
            except ValueError: logging.getLogger('app').exception('handled')
        def test_secrets():
            sqlite3.connect(':memory:').execute('SELECT ?', ('{secret}',))
        """
    )
    if variable is not None and value is not None:
        monkeypatch.setenv(variable, value)

    result = pytester.runpytest_subprocess(
        "--sharpit",
        "--sharpit-app=appmod:app",
        "--sharpit-allow-unknown",
        "--sharpit-report=report.json",
        "--sharpit-junit=report.xml",
        "-q",
    )

    assert result.ret == 0
    json_text = (pytester.path / "report.json").read_text()
    junit_text = (pytester.path / "report.xml").read_text()
    assert secret not in json_text
    assert secret not in junit_text
    data = json.loads(json_text)
    ET.fromstring(junit_text)
    if warning is not None:
        assert warning in data["warnings"]
    assert any(finding["advisor"] == "rest-api" for finding in data["findings"])


def test_plugin_report_corpus_default(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    _run_report_corpus(pytester, monkeypatch, None, None, None)


def test_failed_gate_findings_listed_on_the_test(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import sqlite3
        def test_n_plus_one():
            db = sqlite3.connect(':memory:')
            db.execute('CREATE TABLE owners (id INTEGER)')
            for _ in range(6):
                db.execute('SELECT * FROM owners WHERE id = 1').fetchall()
        """
    )
    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q")

    assert result.ret == 1
    data = json.loads((pytester.path / "report.json").read_text())
    test = next(test for test in data["tests"] if test["nodeId"].endswith("::test_n_plus_one"))
    assert test["findings"]
    assert test["findings"][0].startswith("test-runtime:sharpit.n-plus-one:")
    assert test["findings"][0] == next(
        finding["fingerprint"] for finding in data["findings"] if finding["ruleId"] == "sharpit.n-plus-one"
    )


def test_live_engine_driver_counts_as_covered(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        appmod="""
        import aiosqlite
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        """,
        test_app="def test_no_query(): pass",
    )
    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-app=appmod:engine", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert "untraced database driver in use: aiosqlite" not in data["statusReasons"]


def test_plugin_report_corpus_full_exposure(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    _run_report_corpus(
        pytester, monkeypatch, "SHARPIT_EXPOSE_VALUES", "FULL", "report ignores SHARPIT_EXPOSE_VALUES=FULL"
    )


def test_plugin_report_corpus_masking_off(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    _run_report_corpus(
        pytester, monkeypatch, "SHARPIT_MASK_SECRETS", "false", "report ignores SHARPIT_MASK_SECRETS=false"
    )
