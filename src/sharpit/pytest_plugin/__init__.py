"""pytest >= 8 adapter for sharpit's test-session capture."""

from __future__ import annotations

import importlib
import inspect
import logging
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from functools import wraps
from typing import Any, cast

import pytest

try:
    from pluggy import Result
except ImportError:  # pluggy before the public re-export
    from pluggy._result import Result

from sharpit import __version__
from sharpit.engine import sqla
from sharpit.engine.activation import active_profiles
from sharpit.engine.advisors.findings import AdvisorRun
from sharpit.engine.advisors.rules import Severity
from sharpit.engine.capture.correlation import TEST
from sharpit.engine.collectors.restapi.rules import application_routes
from sharpit.engine.collectors.restapi.service import assess
from sharpit.engine.sources import dispatch, sqlite
from sharpit.engine.spi import ApiModel
from sharpit.engine.testsession import gates, outcome, report
from sharpit.engine.testsession.sink import TestSessionSink, report_masker, report_masker_warnings
from sharpit.fastapi.introspector import FastApiIntrospector
from sharpit.pytest_plugin.marker import budget_for
from sharpit.pytest_plugin.options import PluginOptions, resolve
from sharpit.settings import load_settings, parse_mode

_STATE_ATTR = "_sharpit_pytest_state"
_active_state: _State | None = None


def _record_hook_failure(sink: TestSessionSink, exc: BaseException) -> None:
    warning = f"a sharpit session hook failed ({type(exc).__name__}); some facts may be missing"
    if warning not in sink.facts.warnings:
        sink.facts.warnings.append(warning)
    source = next((item for item in sink.facts.sources if item["name"] == "pytest-plugin"), None)
    if source is None:
        sink.facts.sources.append({"name": "pytest-plugin", "attached": False, "reason": warning, "limitations": []})


def _record_config_hook_failure(config: Any, exc: BaseException) -> None:
    state = getattr(config, _STATE_ATTR, None) or _active_state
    if state is not None:
        _record_hook_failure(state.sink, exc)


class _ExceptionHandler(logging.Handler):
    def __init__(self, sink: TestSessionSink) -> None:
        super().__init__()
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        if not record.exc_info or record.exc_info[1] is None:
            return
        try:
            self.sink.on_exception(record.exc_info[1], "log", TEST.get())
        except Exception as exc:  # noqa: BLE001
            _record_hook_failure(self.sink, exc)


@dataclass
class _State:
    options: PluginOptions
    sink: TestSessionSink
    sqlite_attached: bool
    sqlalchemy_attached: bool
    handler: _ExceptionHandler
    parts: list[Any]
    missing_workers: list[str]
    log_targets: list[logging.Logger]


def _state(config: Any) -> _State | None:
    return getattr(config, _STATE_ATTR, None) or _active_state


def _add_ini(parser: Any) -> None:
    parser.addini("sharpit", "Enable sharpit test capture", type="bool", default=False)
    parser.addini("sharpit_report", "Sharpit JSON report path", default="sharpit-report.json")
    parser.addini("sharpit_junit", "Sharpit JUnit report path", default="")
    parser.addini("sharpit_max_queries", "Default sharpit per-test query budget", type="int", default=None)
    parser.addini("sharpit_fail_on", "Minimum advisor severity that fails", default="HIGH")
    parser.addini("sharpit_allow_unknown", "Allow an unknown capture result", type="bool", default=False)
    parser.addini("sharpit_app", "Application module and attribute", default="")
    parser.addini("sharpit_advisors", "Run application advisors", type="bool", default=True)
    parser.addini("sharpit_max_unattributed", "Maximum unattributed SQL percentage", type="float", default=10.0)


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("sharpit")
    group.addoption(
        "--sharpit", action="store_true", default=None, dest="sharpit", help="capture test SQL and exceptions"
    )
    group.addoption("--sharpit-report", default=None, metavar="PATH", help="JSON report path")
    group.addoption("--sharpit-junit", default=None, metavar="PATH", help="JUnit findings path")
    group.addoption(
        "--sharpit-max-queries", type=int, default=None, metavar="N", help="default call-phase query budget"
    )
    group.addoption("--sharpit-fail-on", default=None, metavar="SEV", help="advisor severity gate")
    group.addoption("--sharpit-allow-unknown", action="store_true", default=None, help="allow unknown capture status")
    group.addoption("--sharpit-app", default=None, metavar="MOD:ATTR", help="application to assess")
    group.addoption(
        "--sharpit-no-advisors",
        action="store_false",
        default=None,
        dest="sharpit_advisors",
        help="run count gates only",
    )
    group.addoption(
        "--sharpit-max-unattributed", type=float, default=None, metavar="PCT", help="unattributed SQL limit"
    )
    _add_ini(parser)


def pytest_configure(config: Any) -> None:
    config.addinivalue_line(
        "markers",
        "sharpit(max_queries=None, allow_n_plus_one=False, max_exceptions=0): per-test capture gate overrides",
    )
    try:
        options = resolve(config)
    except (TypeError, ValueError) as exc:
        raise pytest.UsageError(f"sharpit: {exc}") from exc
    if options.enabled:
        try:
            _validate_activation()
        except ValueError as exc:
            raise pytest.UsageError(str(exc)) from exc
        try:
            _attach(config)  # also covers pytester.runpytest_inprocess, where initial conftests already ran
        except pytest.UsageError:
            raise
        except Exception as exc:  # noqa: BLE001
            _record_config_hook_failure(config, exc)


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    options = resolve(config)
    if options.enabled:
        for item in items:
            budget_for(item, options.max_queries)


def _validate_activation() -> list[str]:
    settings = load_settings({}, os.environ)
    raw_mode = os.environ.get("SHARPIT_ENABLED", "")
    if raw_mode.strip() and parse_mode(raw_mode) is None:
        warning = next((w for w in settings.warnings if "SHARPIT_ENABLED" in w), "invalid SHARPIT_ENABLED value")
        raise ValueError(f"sharpit: --sharpit refused because {warning}")
    mode = parse_mode(settings.enabled)
    if mode is None:
        reason = settings.warnings[0] if settings.warnings else "SHARPIT_ENABLED is invalid"
        raise ValueError(f"sharpit: --sharpit refused because {reason}")
    profiles = active_profiles(settings, os.environ)
    disabled = next((p for p in settings.disabled_profiles if p in profiles), None)
    if disabled and mode != "ON":
        raise ValueError(
            f"sharpit: --sharpit refused because active profile '{disabled}' is in SHARPIT_DISABLED_PROFILES"
        )
    if mode == "OFF":
        raise ValueError("sharpit: --sharpit conflicts with SHARPIT_ENABLED=OFF")
    warnings = list(settings.warnings)
    if disabled and mode == "ON":
        warnings.append(f"Profile '{disabled}' is in SHARPIT_DISABLED_PROFILES but SHARPIT_ENABLED=ON forces it on.")
    return warnings


def _source_state(sink: TestSessionSink, sql_attached: bool) -> None:
    facts = sink.facts
    facts.sources.append(
        {
            "name": "sqlite3",
            "attached": sql_attached,
            "reason": None if sql_attached else "sqlite3 source did not attach",
            "limitations": sqlite.limitations(),
        }
    )
    facts.preexisting = sqlite.preexisting_connections()
    facts.aliases = sqlite.early_aliases()


def _record_sqlalchemy_source(state: _State) -> None:
    source = next((source for source in state.sink.facts.sources if source["name"] == "sqlalchemy"), None)
    if source is None and sqla.sqlalchemy_module() is not None:
        state.sink.facts.sources.append(
            {
                "name": "sqlalchemy",
                "attached": state.sqlalchemy_attached,
                "reason": None if state.sqlalchemy_attached else "SQLAlchemy listeners did not attach",
                "limitations": [],
            }
        )
    elif source is not None:
        source.update(
            attached=state.sqlalchemy_attached,
            reason=None if state.sqlalchemy_attached else "SQLAlchemy listeners did not attach",
        )


def _attach(config: Any) -> None:
    global _active_state  # noqa: PLW0603
    options = resolve(config)
    if not options.enabled or _state(config) is not None:
        return
    try:
        warnings = _validate_activation()
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc
    worker = getattr(config, "workerinput", {}).get("workerid", "master")
    sink = TestSessionSink(worker)
    sink.facts.warnings.extend(warnings)
    sink.facts.warnings.extend(report_masker_warnings(os.environ))
    sink.facts.warnings.extend(load_settings({}, os.environ).warnings)
    handler = _ExceptionHandler(sink)
    state = _State(options, sink, False, False, handler, [], [], [])
    _active_state = state
    setattr(config, _STATE_ATTR, state)
    config.add_cleanup(lambda: _detach(config))
    dispatch.set_session_sink(sink)
    sqlite.attach("pytest-session")
    # attach() returns False when an earlier sharPit holder already owns the patch.
    state.sqlite_attached = sqlite.is_attached()
    state.sqlalchemy_attached = sqla.attach_session()
    _source_state(sink, state.sqlite_attached)
    sink.facts.sources.append(
        {"name": "exceptions", "attached": False, "reason": "no test phase has started", "limitations": []}
    )
    _record_sqlalchemy_source(state)


def _detach(config: Any) -> None:
    global _active_state  # noqa: PLW0603
    state = _state(config)
    if state is None:
        return
    for cleanup in (
        lambda: logging.root.removeHandler(state.handler),
        lambda: dispatch.set_session_sink(None),
        lambda: sqlite.detach("pytest-session"),
        sqla.detach_session,
    ):
        try:
            cleanup()
        except Exception as exc:  # noqa: BLE001
            _record_hook_failure(state.sink, exc)
    if hasattr(config, _STATE_ATTR):
        delattr(config, _STATE_ATTR)
    _active_state = None


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_load_initial_conftests(early_config: Any, parser: Any, args: list[str]) -> Any:
    del parser, args
    enabled = getattr(early_config.known_args_namespace, "sharpit", None)
    try:
        if enabled is None:
            enabled = bool(early_config.getini("sharpit"))
        if enabled:
            _attach(early_config)
    except pytest.UsageError:
        _detach(early_config)
        raise
    except Exception as exc:  # noqa: BLE001
        _record_config_hook_failure(early_config, exc)
    try:
        hook_result = cast(Result[Any], (yield))
        if hook_result.excinfo is not None:
            _detach(early_config)
    except BaseException:
        _detach(early_config)
        raise


def pytest_sessionstart(session: Any) -> None:
    state = _state(session.config)
    if state is None:
        return
    try:
        worker_id = getattr(session.config, "workerinput", {}).get("workerid")
        if worker_id:
            state.sink.facts.worker = worker_id
        if not state.sqlalchemy_attached:
            state.sqlalchemy_attached = sqla.attach_session()
            _record_sqlalchemy_source(state)
    except Exception as exc:  # noqa: BLE001
        _record_hook_failure(state.sink, exc)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: Any, nextitem: Any) -> Any:
    del nextitem
    state = _state(item.config)
    if state:
        try:
            state.sink.begin_test(item.nodeid)
        except Exception as exc:  # noqa: BLE001
            _record_hook_failure(state.sink, exc)
    try:
        yield
    finally:
        if state:
            try:
                state.sink.end_test()
            except Exception as exc:  # noqa: BLE001
                _record_hook_failure(state.sink, exc)


def _phase(item: Any, name: str) -> Any:
    state = _state(item.config)
    if state is None:
        return None
    try:
        current = state.sink.current_test
        if current is None:
            return None
        if not state.sqlalchemy_attached:
            state.sqlalchemy_attached = sqla.attach_session()
            _record_sqlalchemy_source(state)
        token = TEST.set((item.nodeid, current.key.attempt, name))
        state.log_targets = [logging.root]
        state.log_targets.extend(
            logger
            for name, logger in logging.root.manager.loggerDict.items()
            if isinstance(logger, logging.Logger)
            and not logger.propagate
            and logger.handlers
            and name != "sharpit"
            and not name.startswith("sharpit.")
        )
        for logger in state.log_targets:
            logger.addHandler(state.handler)
        exception_source = next(s for s in state.sink.facts.sources if s["name"] == "exceptions")
        exception_source.update(attached=True, reason=None)
        return state, token
    except Exception as exc:  # noqa: BLE001
        _record_hook_failure(state.sink, exc)
        return None


def _phase_done(phase: Any) -> None:
    if phase is None:
        return
    state, token = phase
    try:
        missing = False
        for logger in state.log_targets:
            if state.handler not in logger.handlers:
                missing = True
            logger.removeHandler(state.handler)
        state.log_targets.clear()
        if missing:
            state.sink.facts.exceptions_source_ok = False
            exception_source = next(s for s in state.sink.facts.sources if s["name"] == "exceptions")
            exception_source.update(attached=False, reason="application reconfigured logging during a test phase")
    except Exception as exc:  # noqa: BLE001
        _record_hook_failure(state.sink, exc)
    finally:
        try:
            TEST.reset(token)
        except Exception as exc:  # noqa: BLE001
            _record_hook_failure(state.sink, exc)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item: Any) -> Any:
    state = None
    try:
        state = _state(item.config)
        current = state.sink.current_test if state is not None else None
        if (
            state is not None
            and current is not None
            and current.key.node_id == item.nodeid
            and "call" in current.phases
        ):
            state.sink.begin_test(item.nodeid)
        phase = _phase(item, "setup")
    except Exception as exc:  # noqa: BLE001
        phase = None
        if state is not None:
            _record_hook_failure(state.sink, exc)
    try:
        yield
    finally:
        _phase_done(phase)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: Any) -> Any:
    state = None
    original = getattr(item, "obj", None)
    phase = None
    try:
        state = _state(item.config)
        phase = _phase(item, "call")
        test = state.sink.current_test if state else None
        if state and test and inspect.iscoroutinefunction(original):
            attempt = test.key.attempt

            @wraps(original)
            async def run_in_context(*args: Any, **kwargs: Any) -> Any:
                token = TEST.set((item.nodeid, attempt, "call"))
                try:
                    return await original(*args, **kwargs)
                finally:
                    TEST.reset(token)

            item.obj = run_in_context
    except Exception as exc:  # noqa: BLE001
        if state is not None:
            _record_hook_failure(state.sink, exc)
    try:
        yield
    finally:
        item.obj = original
        _phase_done(phase)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item: Any, nextitem: Any) -> Any:
    del nextitem
    state = _state(item.config)
    try:
        phase = _phase(item, "teardown")
    except Exception as exc:  # noqa: BLE001
        phase = None
        if state is not None:
            _record_hook_failure(state.sink, exc)
    try:
        yield
    finally:
        if phase is not None:
            try:
                phase[0].sink.snapshot_apps(_model_of)
            except Exception as exc:  # noqa: BLE001
                _record_hook_failure(phase[0].sink, exc)
        _phase_done(phase)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Any:
    outcome_result = cast(Result[Any], (yield))
    state = _state(item.config)
    report_obj = outcome_result.get_result()
    if state is None:
        return
    try:
        test = state.sink.current_test
        if test is None:
            return
        if report_obj.when != "call":
            if report_obj.skipped:
                test.outcome = "skipped"
            elif report_obj.failed:
                test.outcome = "error"
            return
        test.outcome = report_obj.outcome
        budget = budget_for(item, state.options.max_queries)
        test.budget = budget
        settings = load_settings({}, os.environ)
        findings = gates.evaluate_test(test, budget, settings.activity_n_plus_one_threshold, ())
        test.findings = [finding.to_dto() for finding in findings]
        messages = [f"sharpit: {finding.rule_id}: {finding.message}" for finding in findings]
        if messages:
            report_obj.longrepr = f"{report_obj.longrepr}\n" if report_obj.failed else ""
            report_obj.longrepr = f"{report_obj.longrepr}{'\n'.join(messages)}"
            report_obj.outcome = "failed"
            test.outcome = "failed"
    except Exception as exc:  # noqa: BLE001
        _record_hook_failure(state.sink, exc)


def _load_app(spec: str) -> tuple[str, object]:
    module_name, separator, attr = spec.partition(":")
    if not separator:
        raise ValueError("--sharpit-app must be MOD:ATTR")
    app = getattr(importlib.import_module(module_name), attr)
    return spec, app() if callable(app) and not hasattr(app, "router") else app


def _model_of(app: object) -> ApiModel:
    return FastApiIntrospector(app).api_model()


def _run_advisors(state: _State) -> None:
    if not state.options.advisors:
        return
    models = state.sink.app_snapshots()
    if state.options.app:
        try:
            name, app = _load_app(state.options.app)
            models = [(name, FastApiIntrospector(app).api_model())]
        except Exception as exc:  # noqa: BLE001
            state.sink.facts.advisor_runs.append(
                AdvisorRun(
                    "rest-api",
                    "UNKNOWN",
                    (),
                    {},
                    f"application could not load ({type(exc).__name__})",
                    state.options.app,
                )
            )
            return
    if not models:
        state.sink.facts.advisor_runs.append(
            AdvisorRun(
                "rest-api", "UNKNOWN", (), {}, "no application: pass --sharpit-app or call sharpit.install in the tests"
            )
        )
        return
    for name, model in models:
        if not application_routes(model.routes) and not state.options.app:
            state.sink.facts.advisor_runs.append(
                AdvisorRun("rest-api", "UNKNOWN", (), {}, "no routes seen after install", name)
            )
        else:
            state.sink.facts.advisor_runs.append(
                assess(model, report_masker(), fail_on=cast("Severity", state.options.fail_on), app=name)
            )


def _advisors(state: _State) -> None:
    try:
        _run_advisors(state)
    except Exception as exc:  # noqa: BLE001
        _record_hook_failure(state.sink, exc)


def _xdist_controller(config: Any, state: _State) -> bool:
    manager = getattr(config, "pluginmanager", None)
    has_dsession = bool(manager and manager.hasplugin("dsession"))
    return has_dsession or bool(state.parts or state.missing_workers)


def _refresh_report_after_hook_failure(state: _State, config: Any, exc: BaseException) -> None:
    data = cast("dict[str, Any] | None", getattr(config, "_sharpit_report", None))
    if not isinstance(data, dict):
        return
    warning = f"a sharpit session hook failed ({type(exc).__name__}); some facts may be missing"
    data["status"] = "unknown"
    source: dict[str, Any] = {"name": "pytest-plugin", "attached": False, "reason": warning, "limitations": []}
    if not any(item.get("name") == "pytest-plugin" for item in data["sources"]):
        data["sources"].append(source)
    reason = warning.replace("a sharpit ", "sharpit ").replace("; some facts may be missing", "")
    if reason not in data["statusReasons"]:
        data["statusReasons"].append(reason)
    if warning not in data["warnings"]:
        data["warnings"].append(warning)
    try:
        report.write_json(state.options.report, data)
        if state.options.junit:
            report.write_junit(state.options.junit, data, allow_unknown=state.options.allow_unknown)
    except Exception as write_exc:  # noqa: BLE001
        _record_hook_failure(state.sink, write_exc)


def _write_report(state: _State, session: Any, exitstatus: int) -> None:
    sink = state.sink
    try:
        if not _xdist_controller(session.config, state):
            _advisors(state)
        facts = sink.facts
        facts.untraced_drivers.update(
            module
            for module in ("aiosqlite", "asyncpg", "psycopg", "psycopg2", "pymysql", "MySQLdb", "oracledb", "pyodbc")
            if module in sys.modules
        )
        facts.engine_drivers.update(dispatch.engine_drivers())
        facts.engine_drivers.update(sqla.live_engine_drivers())
        if _xdist_controller(session.config, state):
            parts = [*state.parts, facts] if facts.warnings else state.parts
        else:
            parts = [facts]
        merged = outcome.merge(parts, state.missing_workers)
        status, reasons = outcome.session_status(
            merged,
            allow_unknown=state.options.allow_unknown,
            max_unattributed=state.options.max_unattributed,
            advisors_enabled=state.options.advisors,
            fail_on=state.options.fail_on,
        )
        data = report.render(
            merged,
            status,
            reasons,
            gates={
                "maxQueriesPerTest": state.options.max_queries,
                "nPlusOneThreshold": load_settings({}, os.environ).activity_n_plus_one_threshold,
                "failOnSeverity": state.options.fail_on,
                "allowUnknown": state.options.allow_unknown,
                "maxUnattributedPercent": state.options.max_unattributed,
            },
            version=__version__,
            now_ms=time.time_ns() // 1_000_000,
            advisors_enabled=state.options.advisors,
        )
        report.write_json(state.options.report, data)
        if state.options.junit:
            report.write_junit(state.options.junit, data, allow_unknown=state.options.allow_unknown)
        if exitstatus == 0 and outcome.exit_fails(status, state.options.allow_unknown):
            session.exitstatus = 1
        session._sharpit_report = data
        session.config._sharpit_report = data
    except Exception as exc:  # noqa: BLE001
        _record_hook_failure(sink, exc)
        if exitstatus == 0:
            session.exitstatus = 1


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    state = None
    try:
        state = _state(session.config)
    except Exception as exc:  # noqa: BLE001
        fallback = _active_state
        if fallback is not None:
            _record_hook_failure(fallback.sink, exc)
        return
    if state is None:
        return
    if hasattr(session.config, "workerinput"):
        _advisors(state)
        try:
            session.config.workeroutput["sharpit"] = state.sink.facts.to_json()
        except Exception as exc:  # noqa: BLE001
            _record_hook_failure(state.sink, exc)
        return
    _write_report(state, session, exitstatus)


def pytest_testnodedown(node: Any, error: Any) -> None:
    state = None
    try:
        state = _state(node.config)
        if state is None:
            return
        _collect_worker_data(state, node, error)
    except Exception as exc:  # noqa: BLE001
        if state is not None:
            _record_hook_failure(state.sink, exc)
            try:
                state.missing_workers.append(getattr(getattr(node, "gateway", None), "id", "unknown"))
            except Exception as append_exc:  # noqa: BLE001
                _record_hook_failure(state.sink, append_exc)


def _collect_worker_data(state: _State, node: Any, error: Any) -> None:
    data = getattr(node, "workeroutput", {}).get("sharpit")
    if error is not None or data is None:
        state.missing_workers.append(node.gateway.id)
    else:
        from sharpit.engine.testsession.facts import SessionFacts

        state.parts.append(SessionFacts.from_json(data))


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: Any) -> None:
    del exitstatus
    data = getattr(config, "_sharpit_report", None)
    if data is None:
        return
    state = _state(config)
    if state is None:
        return
    try:
        terminalreporter.write_sep("=", f"sharpit: {data['status']}")
        terminalreporter.write_line(f"status: {data['status']}")
        terminalreporter.write_line(f"tests with findings: {sum(1 for test in data['tests'] if test['findings'])}")
        counts = Counter(finding["ruleId"] for finding in data["findings"])
        terminalreporter.write_line("gate counts:")
        for rule, count in sorted(counts.items()):
            terminalreporter.write_line(f"  {rule}: {count}")
        terminalreporter.write_line("worst tests:")
        worst = sorted(
            (test for test in data["tests"] if test["findings"]),
            key=lambda test: (-len(test["findings"]), test["nodeId"]),
        )[:5]
        for test in worst:
            terminalreporter.write_line(f"  {test['nodeId']}: {len(test['findings'])} finding(s)")
        if not worst:
            terminalreporter.write_line("  (none)")
        terminalreporter.write_line(f"report: {config.option.sharpit_report or config.getini('sharpit_report')}")
        for warning in data["warnings"]:
            terminalreporter.write_line(f"warning: {warning}")
    except Exception as exc:  # noqa: BLE001
        _record_hook_failure(state.sink, exc)
        _refresh_report_after_hook_failure(state, config, exc)


def pytest_unconfigure(config: Any) -> None:
    try:
        _detach(config)
    except Exception as exc:  # noqa: BLE001
        state = _state(config)
        if state is not None:
            _record_hook_failure(state.sink, exc)
