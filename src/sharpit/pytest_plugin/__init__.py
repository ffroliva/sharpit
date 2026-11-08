"""pytest >= 8 adapter for sharpit's test-session capture."""

from __future__ import annotations

import inspect
import logging
import os
import sys
from collections import Counter as Counter  # compatibility seam: terminal.py resolves it here
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, cast

import pytest

try:
    from pluggy import Result
except ImportError:  # pluggy before the public re-export
    from pluggy._result import Result

from sharpit import __version__ as __version__
from sharpit.engine import sqla
from sharpit.engine.activation import active_profiles
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.capture.correlation import TEST
from sharpit.engine.collectors.restapi.service import assess as assess  # compatibility seam for apps.py
from sharpit.engine.sources import dispatch, sqlite
from sharpit.engine.sqltext import load_key
from sharpit.engine.testsession import gates as gates
from sharpit.engine.testsession import outcome, report
from sharpit.engine.testsession.facts import SessionFacts
from sharpit.engine.testsession.sink import TestSessionSink, report_masker_warnings
from sharpit.pytest_plugin.apps import (
    load_app as _load_app,
)
from sharpit.pytest_plugin.apps import (
    model_of as _model_of,
)
from sharpit.pytest_plugin.apps import (
    run_advisors as _run_advisors_impl,
)
from sharpit.pytest_plugin.marker import budget_for
from sharpit.pytest_plugin.options import PluginOptions
from sharpit.pytest_plugin.options import pytest_addoption as pytest_addoption
from sharpit.pytest_plugin.options import resolve as resolve
from sharpit.pytest_plugin.report_io import write_report as _write_report  # noqa: F401 - compatibility re-export
from sharpit.pytest_plugin.session import pytest_collection_finish as pytest_collection_finish
from sharpit.pytest_plugin.session import pytest_deselected as pytest_deselected
from sharpit.pytest_plugin.session import pytest_runtest_makereport as pytest_runtest_makereport
from sharpit.pytest_plugin.session import pytest_sessionfinish as pytest_sessionfinish
from sharpit.pytest_plugin.terminal import pytest_terminal_summary as pytest_terminal_summary
from sharpit.settings import SharpitSettings, load_settings, parse_mode

_STATE_ATTR = "_sharpit_pytest_state"
_HOOK_FAILURE_WARNING = "a sharpit session hook failed ({}); some facts may be missing"
_active_state: _State | None = None

__all__ = [
    "pytest_addoption",
    "pytest_configure",
    "pytest_collection_modifyitems",
    "pytest_collection_finish",
    "pytest_deselected",
    "pytest_sessionstart",
    "pytest_runtest_protocol",
    "pytest_runtest_setup",
    "pytest_runtest_call",
    "pytest_runtest_teardown",
    "pytest_runtest_makereport",
    "pytest_sessionfinish",
    "pytest_testnodedown",
    "pytest_terminal_summary",
    "pytest_unconfigure",
    "_load_app",
    "_model_of",
    "_run_advisors",
    "_write_report",
    "_advisors",
    "_xdist_controller",
    "_refresh_report_after_hook_failure",
    "_final_facts",
]


def _record_hook_failure(sink: TestSessionSink, exc: BaseException) -> None:
    warning = _HOOK_FAILURE_WARNING.format(type(exc).__name__)
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
    settings: SharpitSettings
    dismissed: list[str]
    dismissed_pairs: set[tuple[str, str]]
    baseline_observed: dict[str, int | None] | None
    baseline_data: Any | None
    sqlite_attached: bool
    sqlalchemy_attached: bool
    handler: _ExceptionHandler
    parts: list[Any]
    missing_workers: list[str]
    log_targets: list[logging.Logger]
    logger_cache: tuple[logging.Logger, ...]
    logger_cache_size: int
    partial_deselected: int = 0
    partial_collected: int | None = None
    partial_run_count: int = 0
    partial_selection: bool = False
    worker_partial_facts: list[dict[str, Any]] | None = None
    partial: bool = False
    baseline_carried: tuple[Any, ...] = ()


def _state(config: Any) -> _State | None:
    return getattr(config, _STATE_ATTR, None) or _active_state


def _run_advisors(state: _State) -> None:
    _run_advisors_impl(state, load_app=_load_app, assess_fn=assess)


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
    source = next((s for s in facts.sources if s["name"] == "sqlite3"), None)
    identity_unavailable = facts.sqlite_seen and sink.masker.identity_key is None
    if identity_unavailable:
        reason = "SQLite statement identities are unavailable because sharpit could not load a state key"
    elif sql_attached:
        reason = None
    else:
        reason = "sqlite3 source did not attach"
    details = {
        "attached": sql_attached and not identity_unavailable,
        "reason": reason,
        "limitations": sqlite.limitations(),
    }
    if source is None:
        facts.sources.append({"name": "sqlite3", **details})
    else:
        source.update(details)
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
    settings = load_settings({}, os.environ)
    loaded_baseline = None
    try:
        from sharpit.engine.testsession import baseline as baseline_io

        loaded_baseline = baseline_io.read(options.baseline) if options.baseline else None
    except (OSError, ValueError, RecursionError) as exc:
        # fails closed: the session runs and the unusable baseline is an unknown reason (never sharpit off)
        reason = f"baseline unusable: {exc}"
        sink.facts.sources.append({"name": "baseline", "attached": False, "reason": reason, "limitations": []})
    sink.facts.warnings.extend(warnings)
    sink.facts.warnings.extend(report_masker_warnings(os.environ))
    sink.facts.warnings.extend(settings.warnings)
    handler = _ExceptionHandler(sink)
    dismissals = DismissalStore(Path(settings.state_dir))
    try:
        dismissed = dismissals.list()
        dismissed_pairs = dismissals.dismissed_pairs()
    except (OSError, ValueError) as exc:
        dismissed = []
        dismissed_pairs = set[tuple[str, str]]()
        sink.facts.sources.append(
            {"name": "dismissals", "attached": False, "reason": f"dismissals unusable: {exc}", "limitations": []}
        )
    state = _State(
        options,
        sink,
        settings,
        dismissed,
        dismissed_pairs,
        {key: entry.observed for key, entry in loaded_baseline.entries.items()} if loaded_baseline else None,
        loaded_baseline,
        False,
        False,
        handler,
        [],
        [],
        [],
        (),
        -1,
        worker_partial_facts=[],
    )
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
    key_errors: list[OSError | ValueError] = []
    try:
        identity_key = (
            state.settings.identity_key.encode("utf-8")
            if state.settings.identity_key
            else load_key(Path(state.settings.state_dir), create=True, on_error=key_errors.append)
        )
        state.sink.set_identity_key(identity_key)
        sqla.set_identity_key(identity_key)
        if identity_key is None:
            warning = "SQLite statement identities are unavailable because sharpit could not load a state key"
            if key_errors:
                error = key_errors[0]
                warning += f" ({type(error).__name__}: {error})"
            if warning not in state.sink.facts.warnings:
                state.sink.facts.warnings.append(warning)
        worker_id = getattr(session.config, "workerinput", {}).get("workerid")
        if worker_id:
            state.sink.facts.worker = worker_id
        attached = sqla.attach_session()
        if attached and not state.sqlalchemy_attached:
            state.sqlalchemy_attached = True
            _record_sqlalchemy_source(state)
        sqla.set_unbounded_read_factor(state.settings.activity_unbounded_read_factor)
    except Exception as exc:  # noqa: BLE001
        _record_hook_failure(state.sink, exc)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: Any, nextitem: Any) -> Any:
    del nextitem
    state = _state(item.config)
    if state:
        try:
            state.partial_run_count += 1
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
        attached = sqla.attach_session()
        if attached and not state.sqlalchemy_attached:
            state.sqlalchemy_attached = True
            _record_sqlalchemy_source(state)
        token = TEST.set((item.nodeid, current.key.attempt, name))
        logger_dict = logging.root.manager.loggerDict
        if state.logger_cache_size != len(logger_dict):
            state.logger_cache = tuple(
                logger
                for name, logger in logger_dict.items()
                if isinstance(logger, logging.Logger)
                and not logger.propagate
                and logger.handlers
                and name != "sharpit"
                and not name.startswith("sharpit.")
            )
            state.logger_cache_size = len(logger_dict)
        state.log_targets = [logging.root, *state.logger_cache]
        for logger in state.log_targets:
            logger.addHandler(state.handler)
        exception_source = next(s for s in state.sink.facts.sources if s["name"] == "exceptions")
        if state.sink.facts.exceptions_source_ok:
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
    warning = _HOOK_FAILURE_WARNING.format(type(exc).__name__)
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


def _final_facts(state: _State) -> SessionFacts:
    sink = state.sink
    try:
        sink.snapshot_apps(_model_of, force=True)
    except Exception as exc:  # noqa: BLE001
        _record_hook_failure(sink, exc)
    facts = sink.facts
    facts.untraced_drivers.update(module for module in outcome.DRIVER_DIALECTS if module in sys.modules)
    facts.engine_drivers.update(dispatch.engine_drivers())
    facts.engine_drivers.update(sqla.live_engine_drivers())
    _source_state(sink, state.sqlite_attached)
    return facts


@pytest.hookimpl(optionalhook=True)
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


def pytest_unconfigure(config: Any) -> None:
    try:
        _detach(config)
    except Exception as exc:  # noqa: BLE001
        state = _state(config)
        if state is not None:
            _record_hook_failure(state.sink, exc)
