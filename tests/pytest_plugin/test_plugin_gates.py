from __future__ import annotations

import json
from sqlite3 import connect as _EARLY_CONNECT

import pytest


def test_n_plus_one_fails_the_test(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import sqlite3

        def test_repeated_selects():
            connection = sqlite3.connect(':memory:')
            for _ in range(5):
                connection.execute('SELECT 1').fetchone()
        """
    )

    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 1
    assert "sharpit: sharpit.n-plus-one" in result.stdout.str()
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "fail"
    assert data["tests"][0]["findings"]


def test_marker_budget(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import sqlite3
        import pytest

        @pytest.mark.sharpit(max_queries=1)
        def test_one_over_budget():
            connection = sqlite3.connect(':memory:')
            connection.execute('SELECT 1')
            connection.execute('SELECT 2')
        """
    )

    result = pytester.runpytest("--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "-q")

    assert result.ret == 1
    assert "sharpit.max-queries" in result.stdout.str()


def test_marker_unknown_argument(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import pytest
        @pytest.mark.sharpit(typo=1)
        def test_marked(): pass
        """
    )

    result = pytester.runpytest("--sharpit", "-q")

    assert result.ret == 4
    assert "sharpit marker: unknown argument 'typo'" in result.stderr.str()


def test_failed_test_keeps_failure_and_sharpit_lines(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import sqlite3
        def test_both_failures():
            connection = sqlite3.connect(':memory:')
            for _ in range(5): connection.execute('SELECT 1')
            assert False, 'original failure'
        """
    )

    result = pytester.runpytest("--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "-q")

    assert result.ret == 1
    assert "original failure" in result.stdout.str()
    assert "sharpit.n-plus-one" in result.stdout.str()


def test_swallowed_logged_exception_fails(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import logging
        def test_logged_exception():
            try: raise ValueError('sk_live_12345678901234567890')
            except ValueError: logging.getLogger('application').exception('handled')
        """
    )

    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 1
    assert "sharpit.exception" in result.stdout.str()
    assert "sk_live_12345678901234567890" not in (pytester.path / "report.json").read_text()


def test_setup_failure_is_reported_as_error(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("import pytest\n@pytest.fixture\ndef broken(): raise RuntimeError('setup')")
    pytester.makepyfile("def test_setup(broken): pass")

    pytester.runpytest(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    import json

    data = json.loads((pytester.path / "report.json").read_text())
    assert data["tests"][0]["outcome"] == "error"


def test_rerun_last_attempt_decides(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import sqlite3
        import pytest
        attempts = 0
        @pytest.mark.flaky(reruns=1)
        def test_eventually_passes():
            global attempts
            if attempts == 0:
                attempts += 1
                connection = sqlite3.connect(':memory:')
                for _ in range(5): connection.execute('SELECT 1')
                assert False
        """
    )

    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 0
    import json

    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "pass"
    assert len(data["tests"]) == 2
    assert data["findings"] == []


def test_terminal_summary_block_rendered(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_empty(): pass")

    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=custom.json", "-q"
    )

    assert "sharpit: pass" in result.stdout.str()
    assert "gate counts:" in result.stdout.str()
    assert "worst tests:" in result.stdout.str()
    assert "report: custom.json" in result.stdout.str()


def test_finalizer_logged_exception_is_unattributed(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import gc
        import logging
        leaked = None
        class Leaker:
            def __del__(self):
                try: raise ValueError('sk_live_12345678901234567890')
                except ValueError: logging.getLogger('app').exception('finalizer')
        def test_a_leak():
            global leaked
            leaked = Leaker()
        def test_b_collect():
            global leaked
            leaked = None
            gc.collect()
        """
    )

    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["tests"][1]["findings"] == []
    assert data["totals"]["exceptions"] == 1


def test_logging_reconfigured_mid_test_makes_status_unknown(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import logging.config
        def test_reconfigure():
            logging.config.dictConfig({'version': 1, 'handlers': {}, 'root': {'handlers': [], 'level': 'WARNING'}})
        """
    )

    result = pytester.runpytest(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "unknown"
    assert any("exception capture was lost" in reason for reason in data["statusReasons"])


def test_early_connection_limitation_in_report(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_empty(): pass")
    assert callable(_EARLY_CONNECT)

    pytester.runpytest("--sharpit", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q")

    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "unknown"
    assert any("_EARLY_CONNECT" in reason for reason in data["statusReasons"])


def test_pytest_failure_code_never_lowered(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_fails(): assert False")

    result = pytester.runpytest(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 1


def test_plugin_hook_raises_session_continues(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(
        """
        from sharpit.engine.testsession import gates
        def broken(*args, **kwargs): raise RuntimeError('hook')
        gates.evaluate_test = broken
        """
    )
    pytester.makepyfile("def test_continues(): assert True")

    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert any("session hook failed (RuntimeError)" in warning for warning in data["warnings"])


def test_dictconfig_in_conftest_keeps_basicconfig_working(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(
        """
        import logging
        import logging.config
        logging.config.dictConfig({'version': 1, 'handlers': {}, 'root': {'handlers': [], 'level': 'WARNING'}})
        logging.basicConfig(level=logging.INFO)
        assert logging.root.level == logging.INFO
        """
    )
    pytester.makepyfile("def test_empty(): pass")

    result = pytester.runpytest("--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "-q")

    assert result.ret == 0


def test_pytest_raises_escaped_not_counted(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    pytester.makepyfile(
        """
        import pytest
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from sharpit.fastapi.adapter import install
        app = FastAPI()
        @app.get('/error')
        def error(): raise ValueError('sk_live_12345678901234567890')
        install(app, show_banner=False)
        def test_raises():
            with pytest.raises(ValueError): TestClient(app).get('/error')
        """
    )
    monkeypatch.setenv("SHARPIT_ENABLED", "ON")

    result = pytester.runpytest(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["tests"][0]["findings"] == []
