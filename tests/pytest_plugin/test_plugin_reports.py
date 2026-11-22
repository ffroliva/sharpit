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
    secret = "sk_live_" + "12345678901234567890"
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

    result = pytester.runpytest_inprocess(
        "--sharpit",
        "-n",
        "0",
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
    result = pytester.runpytest_inprocess("--sharpit", "--sharpit-report=report.json", "-q")

    assert result.ret == 1
    data = json.loads((pytester.path / "report.json").read_text())
    test = next(test for test in data["tests"] if test["nodeId"].endswith("::test_n_plus_one"))
    assert test["findings"]
    assert test["findings"][0].startswith("test-runtime:sharpit.n-plus-one:")
    assert test["findings"][0] == next(
        finding["fingerprint"] for finding in data["findings"] if finding["ruleId"] == "sharpit.n-plus-one"
    )


@pytest.mark.needs_sqlalchemy
def test_live_engine_driver_counts_as_covered(pytester: pytest.Pytester) -> None:
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("aiosqlite")
    pytester.makepyfile(
        appmod="""
        import aiosqlite
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        """,
        # imported by the tests, so the driver is loaded when the session's facts are taken
        test_app="import appmod\n\ndef test_no_query(): pass",
    )
    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q")

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


@pytest.mark.parametrize("exposure", ("MASKED", "METADATA_ONLY", "FULL"))
def test_binding_diagnostic_sentinels_do_not_enter_pytest_outputs(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, exposure: str
) -> None:
    field = "S3NT1NEL9f3c"
    jwt = "eyJhbGciOiJIUzI1NiJ9.S3NT1NEL9f3c.signature"
    monkeypatch.setenv("SHARPIT_EXPOSE_VALUES", exposure)
    pytester.makepyfile(
        appmod="""
        from fastapi import FastAPI
        from pydantic import BaseModel, ConfigDict
        app = FastAPI()
        class Payload(BaseModel):
            model_config = ConfigDict(extra='forbid')
            value: int
        @app.post('/payload')
        def payload(data: Payload): return data
        """,
        test_binding=f"""
        from fastapi.testclient import TestClient
        from appmod import app
        def test_binding_request():
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post('/payload', json={{'{field}': '{jwt}'}})
            assert response.status_code == 422
        """,
    )

    result = pytester.runpytest_inprocess(
        "--sharpit",
        "--sharpit-app=appmod:app",
        "--sharpit-allow-unknown",
        "--sharpit-report=report.json",
        "--sharpit-junit=report.xml",
        "--sharpit-sarif=report.sarif",
        "-q",
    )

    terminal = result.stdout.str()
    json_report = (pytester.path / "report.json").read_text()
    junit_report = (pytester.path / "report.xml").read_text()
    sarif_report = (pytester.path / "report.sarif").read_text()
    assert result.ret == 0
    sentinels = (field, jwt)
    assert all(sentinel not in terminal for sentinel in sentinels)
    assert all(sentinel not in json_report for sentinel in sentinels)
    assert all(sentinel not in junit_report for sentinel in sentinels)
    assert all(sentinel not in sarif_report for sentinel in sentinels)
    (pytester.path / f"binding-pytest-{exposure}.jsonl").write_text(
        "".join(
            json.dumps({"exposure": exposure, "surface": surface, "text": text}) + "\n"
            for surface, text in (
                ("pytest terminal", terminal),
                ("pytest JSON", json_report),
                ("pytest JUnit", junit_report),
                ("pytest SARIF", sarif_report),
            )
        ),
        encoding="utf-8",
    )


def test_default_terminal_counts_notes_but_reports_keep_findings(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        appmod="""
        from fastapi import FastAPI
        app = FastAPI()
        @app.get('/items')
        def items(): return []
        @app.post('/getUsers')
        def get_users(): return []
        """,
        test_notes="def test_ok(): pass",
    )

    result = pytester.runpytest_inprocess(
        "--sharpit",
        "--sharpit-app=appmod:app",
        "--sharpit-allow-unknown",
        "--sharpit-report=report.json",
        "--sharpit-junit=report.xml",
        "-q",
    )

    stdout = result.stdout.str()
    data = json.loads((pytester.path / "report.json").read_text())
    rules = [f["ruleId"] for f in data["findings"]]
    cases = ET.parse(pytester.path / "report.xml").getroot().findall("testcase")
    assert f"sharpit: {len(rules)} advisor notes in report.json" in stdout
    assert "  RAPI-DOC-001" not in stdout
    assert "RAPI-DOC-001" not in rules
    assert "RAPI-DTO-002" in rules
    assert len(cases) == len(rules) + 1
