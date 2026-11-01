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


def test_fail_on_medium_gates_medium_findings(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        appmod="from fastapi import FastAPI\napp=FastAPI()\n"
        "def handler(): return 1\napp.add_api_route('/items', handler, methods=['GET','POST'])"
    )
    pytester.makepyfile("def test_empty(): pass")

    result = pytester.runpytest_subprocess(
        "--sharpit",
        "--sharpit-app=appmod:app",
        "--sharpit-fail-on=MEDIUM",
        "--sharpit-allow-unknown",
        "--sharpit-report=report.json",
        "-q",
    )

    assert result.ret == 1
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "fail"
    assert any(finding["severity"] == "MEDIUM" for finding in data["findings"])


def test_committed_dismissals_are_honoured(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        appmod="from fastapi import FastAPI\napp=FastAPI()\n"
        "def handler(): return 1\napp.add_api_route('/items', handler, methods=['GET','POST'])"
    )
    pytester.makepyfile(
        "import sqlite3\ndef test_repeated_selects():\n"
        " c=sqlite3.connect(':memory:')\n"
        " for _ in range(5): c.execute('SELECT 1').fetchone()"
    )
    args = [
        "--sharpit",
        "--sharpit-app=appmod:app",
        "--sharpit-fail-on=MEDIUM",
        "--sharpit-allow-unknown",
        "--sharpit-report=report.json",
        "-q",
    ]
    first = pytester.runpytest_subprocess(*args)
    assert first.ret == 1
    before = json.loads((pytester.path / "report.json").read_text())
    n_plus_one = next(f["fingerprint"] for f in before["findings"] if f["advisor"] == "test-runtime")
    rest_rule = next(f["ruleId"] for f in before["findings"] if f["advisor"] == "rest-api")
    state_dir = pytester.path / ".sharpit"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "sharpit.yml").write_text(f"dismissedRules:\n  - {n_plus_one}\n  - {rest_rule}\n")
    second = pytester.runpytest_subprocess(*args)
    assert second.ret == 0, second.stdout.str() + second.stderr.str()
    after = json.loads((pytester.path / "report.json").read_text())
    assert next(f["dismissed"] for f in after["findings"] if f["fingerprint"] == n_plus_one)
    assert next(f["dismissed"] for f in after["findings"] if f["ruleId"] == rest_rule)
    assert after["status"] == "pass"


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


def test_logging_lost_in_setup_stays_lost(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import logging.config
        def test_reconfigure():
            logging.config.dictConfig({'version': 1, 'handlers': {}, 'root': {'handlers': [], 'level': 'WARNING'}})
        def test_after_reconfigure(): pass
        """
    )
    result = pytester.runpytest(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )
    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert any("exception capture was lost" in reason for reason in data["statusReasons"])
    source = next(s for s in data["sources"] if s["name"] == "exceptions")
    assert source["attached"] is False
    assert source["reason"] == "application reconfigured logging during a test phase"
    assert data["status"] == "unknown"


def test_early_connection_limitation_in_report(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_empty(): pass")
    assert callable(_EARLY_CONNECT)

    pytester.runpytest("--sharpit", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q")

    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "unknown"
    assert any("_EARLY_CONNECT" in reason for reason in data["statusReasons"])


def test_factory_pass_through_limitation_reaches_report(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import sqlite3
        def test_factory():
            try:
                sqlite3.connect(':memory:', factory=lambda: None)
            except TypeError:
                pass
        """
    )
    result = pytester.runpytest(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )
    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    source = next(item for item in data["sources"] if item["name"] == "sqlite3")
    assert any("factory or cursor class" in limitation for limitation in source["limitations"])


def test_pytest_failure_code_never_lowered(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_fails(): assert False")

    result = pytester.runpytest(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 1


@pytest.mark.parametrize(
    ("patch", "xdist", "advisors"),
    [
        ("begin_test", False, False),
        ("phase", False, False),
        ("makereport", False, False),
        ("sessionstart", False, False),
        ("testnodedown", True, False),
        ("terminal_summary", False, False),
        ("worker_advisors", True, True),
    ],
)
def test_plugin_hook_raises_session_continues(
    pytester: pytest.Pytester, patch: str, xdist: bool, advisors: bool
) -> None:
    pytester.makeconftest(
        f"""
        import sharpit.pytest_plugin as plugin
        from sharpit.engine.testsession.sink import TestSessionSink
        from sharpit.engine.testsession import gates
        from sharpit.engine import sqla

        def broken(*args, **kwargs): raise RuntimeError('injected')
        if {patch!r} == 'begin_test':
            TestSessionSink.begin_test = broken
        elif {patch!r} == 'phase':
            plugin._phase = broken
        elif {patch!r} == 'makereport':
            gates.evaluate_test = broken
        elif {patch!r} == 'sessionstart':
            if plugin._active_state is not None:
                plugin._active_state.sqlalchemy_attached = False
            sqla.attach_session = broken
        elif {patch!r} == 'testnodedown':
            plugin._collect_worker_data = broken
        elif {patch!r} == 'terminal_summary':
            plugin.Counter = broken
        elif {patch!r} == 'worker_advisors':
            plugin.assess = broken
        """
    )
    app_arg = ""
    if advisors:
        pytester.makepyfile(appmod="from fastapi import FastAPI\napp=FastAPI()\n@app.get('/x')\ndef x(): return 1")
        app_arg = "--sharpit-app=appmod:app"
    pytester.makepyfile("def test_continues(): assert True")
    args = ["-n", "2"] if xdist else []
    if not advisors:
        args.append("--sharpit-no-advisors")
    result = pytester.runpytest_subprocess(
        *args,
        "--sharpit",
        "--sharpit-allow-unknown",
        "--sharpit-report=report.json",
        *([app_arg] if app_arg else []),
        "-q",
    )

    assert result.ret == 0
    output = result.stdout.str() + result.stderr.str()
    assert "INTERNALERROR" not in output
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "unknown"
    assert sum("session hook failed (RuntimeError)" in warning for warning in data["warnings"]) == 1
    assert any(source["name"] == "pytest-plugin" and not source["attached"] for source in data["sources"])


def test_snapshot_failure_does_not_error_the_test(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(
        "from sharpit.engine.testsession.sink import TestSessionSink\n"
        "def broken(*args, **kwargs): raise RuntimeError('snapshot')\n"
        "TestSessionSink.snapshot_apps = broken\n"
    )
    pytester.makepyfile("def test_passes(): assert True")

    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 0
    assert "1 passed" in result.stdout.str()
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "unknown"
    assert sum("session hook failed (RuntimeError)" in warning for warning in data["warnings"]) == 1
    assert any(source["name"] == "pytest-plugin" and not source["attached"] for source in data["sources"])


def test_early_attach_failure_does_not_interrupt_session(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        sitecustomize="""
        from sharpit.engine.sources import sqlite
        def broken(*args, **kwargs): raise RuntimeError('early attach')
        sqlite.attach = broken
        """
    )
    pytester.makepyfile("def test_passes(): assert True")

    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q")

    assert result.ret == 0
    assert "1 passed" in result.stdout.str()
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "unknown"
    assert sum("session hook failed (RuntimeError)" in warning for warning in data["warnings"]) == 1
    assert any(source["name"] == "pytest-plugin" and not source["attached"] for source in data["sources"])


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
