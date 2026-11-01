from __future__ import annotations

import json
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


def test_plugin_loads_without_xdist(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_pass(): assert True")
    plain = pytester.runpytest_subprocess("-p", "no:xdist", "-q")
    enabled = pytester.runpytest_subprocess(
        "-p", "no:xdist", "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "-q"
    )
    assert plain.ret == 0
    assert enabled.ret == 0


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


def test_xdist_app_seen_by_one_worker_passes(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        def test_register_app():
            from fastapi import FastAPI
            import sharpit
            app = FastAPI()
            app.get('/ok')(lambda: {'ok': True})
            sharpit.install(app)
        """
    )
    result = pytester.runpytest_subprocess(
        "-n", "2", "--sharpit", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )
    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["advisors"][0]["status"] == "PASSED"


def test_xdist_untraced_driver_unknown(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import sys, types
        sys.modules['asyncpg'] = types.ModuleType('asyncpg')
        import sqlite3
        def test_sql(): sqlite3.connect(':memory:').execute('SELECT 1')
        """
    )
    result = pytester.runpytest_subprocess(
        "-n", "2", "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )
    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert any("untraced database driver in use: asyncpg" in r for r in data["statusReasons"])


def test_controller_warning_does_not_add_a_master_worker(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytester.makepyfile("import sqlite3\ndef test_sql(): sqlite3.connect(':memory:').execute('SELECT 1')")
    monkeypatch.setenv("SHARPIT_EXPOSE_VALUES", "FULL")
    result = pytester.runpytest_subprocess(
        "-n", "2", "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )
    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert "master" not in {worker["id"] for worker in data["workers"]}


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


def test_xdist_controller_never_imports_app_code(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        appmod="import os\nfrom pathlib import Path\n"
        "Path('imports.txt').open('a').write(os.environ.get('PYTEST_XDIST_WORKER', 'controller') + '\\n')\n"
        "from fastapi import FastAPI\napp=FastAPI()\n@app.get('/x')\ndef x(): return 1"
    )
    pytester.makepyfile("def test_a(): pass\ndef test_b(): pass")

    result = pytester.runpytest_subprocess(
        "-n",
        "2",
        "--sharpit",
        "--sharpit-app=appmod:app",
        "--sharpit-allow-unknown",
        "--sharpit-report=report.json",
        "-q",
    )

    assert result.ret == 0
    imports = (pytester.path / "imports.txt").read_text().splitlines()
    assert "controller" not in imports


def test_xdist_crashed_worker_unknown(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("import os\ndef test_a(): pass\ndef test_crash(): os._exit(1)")

    result = pytester.runpytest_subprocess(
        "-n", "2", "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret != 3
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "unknown"
    assert any(worker["status"] == "missing" for worker in data["workers"])


def test_xdist_each_worker_restores(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(
        """
        import pathlib
        import sqlite3
        import pytest
        @pytest.hookimpl(hookwrapper=True, tryfirst=True)
        def pytest_unconfigure(config):
            yield
            worker = getattr(config, 'workerinput', {}).get('workerid')
            if worker:
                pathlib.Path(f'restored-{worker}.txt').write_text(str(sqlite3.connect is sqlite3.dbapi2.connect))
        """
    )
    pytester.makepyfile(
        "import sqlite3\ndef test_a(): sqlite3.connect(':memory:')\ndef test_b(): sqlite3.connect(':memory:')"
    )

    result = pytester.runpytest_subprocess(
        "-n",
        "2",
        "--dist=each",
        "--sharpit",
        "--sharpit-no-advisors",
        "--sharpit-allow-unknown",
        "--sharpit-report=report.json",
        "-q",
    )

    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert {worker["status"] for worker in data["workers"]} == {"ok"}
    assert {test["worker"] for test in data["tests"]} == {"gw0", "gw1"}
    assert (pytester.path / "restored-gw0.txt").read_text() == "True"
    assert (pytester.path / "restored-gw1.txt").read_text() == "True"


def test_xdist_tx_without_n_merges(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("import sqlite3\ndef test_a(): sqlite3.connect(':memory:').execute('SELECT 1')")
    result = pytester.runpytest_subprocess(
        "--tx=popen",
        "--sharpit",
        "--sharpit-no-advisors",
        "--sharpit-allow-unknown",
        "--sharpit-report=report.json",
        "-q",
    )
    if "--tx" in result.stderr.str() or "unrecognized arguments" in result.stderr.str():
        pytest.skip("pytest-xdist does not provide --tx popen on this platform")

    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["totals"]["queries"] == 1
