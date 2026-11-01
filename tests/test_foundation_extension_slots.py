"""Lane F Task 2: the inert 0.4 extension slots later lanes consume (F-foundation.md interface table, council R1/R4/R12/R17)."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.capture import CaptureState
from sharpit.engine.capture.correlation import REQUEST
from sharpit.fastapi.capture import CaptureWiring, wiring_of
from sharpit.settings import load_settings

SETTINGS_0_4: dict[str, Any] = {
    "security_logs_max_logs": 500,
    "postgresql_max_sessions": 100,
    "postgresql_max_statements": 100,
    "postgresql_max_indexes": 500,
    "postgresql_max_tables": 200,
    "postgresql_max_vacuum_tables": 200,
    "postgresql_max_replicas": 10,
    "postgresql_max_settings": 40,
    "transactions_enabled": True,
    "transactions_recording": True,
    "transactions_max_entries": 200,
    "transactions_slow_transaction_threshold_millis": 200,
    "transactions_connection_hold_threshold_millis": 500,
    "activity_unbounded_read_factor": 2,
}


def test_0_4_settings_defaults() -> None:
    s = load_settings({}, {})
    assert {name: getattr(s, name, None) for name in SETTINGS_0_4} == SETTINGS_0_4
    assert s.warnings == ()


@pytest.mark.parametrize(
    ("field", "raw", "expected"),
    [
        ("postgresql_max_sessions", "2147483646", 2147483646),
        ("postgresql_max_sessions", "2147483647", 100),
        ("postgresql_max_settings", "0", 40),
        ("activity_unbounded_read_factor", "1", 2),
        ("activity_unbounded_read_factor", "7", 7),
        ("transactions_recording", "false", False),
        ("security_logs_max_logs", "lots", 500),
    ],
)
def test_0_4_settings_env_parsers(field: str, raw: str, expected: object) -> None:
    s = load_settings({}, {f"SHARPIT_{field.upper()}": raw})
    assert getattr(s, field, None) == expected


class _Untouchable:
    """A model stand-in that records any attribute access: install() must never inspect a model."""

    touched: list[str] = []

    def __getattribute__(self, name: str) -> Any:
        type(self).touched.append(name)
        return object.__getattribute__(self, name)


def test_models_hook_stores_models_without_side_effects() -> None:
    first, second = _Untouchable(), _Untouchable()
    _Untouchable.touched.clear()

    handle = install(FastAPI(), enabled="ON", show_banner=False, models=[first, second])

    models: tuple[object, ...] = getattr(handle.context, "models", ())
    assert len(models) == 2
    assert models[0] is first
    assert models[1] is second
    assert _Untouchable.touched == []
    assert getattr(install(FastAPI(), enabled="ON", show_banner=False).context, "models", None) == ()


def test_models_hook_accepts_a_lone_declarative_base() -> None:
    class Base:  # install(models=Base): a lone class is one element, never iterated
        pass

    handle = install(FastAPI(), enabled="ON", show_banner=False, models=Base)
    assert getattr(handle.context, "models", None) == (Base,)


def test_dismissed_pairs_is_inert_empty_set(tmp_path: Path) -> None:
    store = DismissalStore(tmp_path)
    store.add("RAPI-NAME-001")
    assert store.dismissed_pairs() == set()


def test_capture_slots_default_inert() -> None:
    state = CaptureState()
    wiring = CaptureWiring()
    assert getattr(state, "security_logs", "missing") is None
    assert getattr(state, "transactions", "missing") is None
    assert getattr(state, "teardowns", None) == []
    assert getattr(wiring, "on_security_event", "missing") is None
    assert getattr(wiring, "span_processor", "missing") is None


def _app_with_statuses() -> FastAPI:
    app = FastAPI()
    for code in (200, 401, 403):
        app.get(f"/s{code}")(lambda code=code: PlainTextResponse("x", status_code=code))
    return app


def test_security_event_hook_sees_request_id() -> None:
    app = _app_with_statuses()
    handle = install(app, enabled="ON", show_banner=False)
    wiring = wiring_of(handle.context)
    assert wiring is not None
    seen: list[tuple[str, str, int, bool]] = []

    def hook(scope: Any, status: int) -> None:
        info = REQUEST.get()
        seen.append((scope["method"], scope["path"], status, info is not None and bool(info.id)))

    wiring.on_security_event = hook
    with TestClient(app) as client:
        for code in (200, 401, 403):
            client.get(f"/s{code}")

    assert seen == [("GET", "/s401", 401, True), ("GET", "/s403", 403, True)]


def test_security_event_hook_failure_never_changes_the_response() -> None:
    app = _app_with_statuses()
    handle = install(app, enabled="ON", show_banner=False)
    wiring = wiring_of(handle.context)
    assert wiring is not None

    def broken(scope: Any, status: int) -> None:
        raise RuntimeError("hook bug")

    wiring.on_security_event = broken
    with TestClient(app) as client:
        assert client.get("/s401").status_code == 401


def test_uninstall_runs_teardowns_in_reverse_even_if_one_fails() -> None:
    handle = install(FastAPI(), enabled="ON", show_banner=False)
    ran: list[str] = []

    def failing() -> None:
        ran.append("second")
        raise RuntimeError("teardown bug")

    teardowns: list[Callable[[], None]] = getattr(handle.context.capture, "teardowns", [])
    teardowns.extend([lambda: ran.append("first"), failing, lambda: ran.append("third")])

    handle.uninstall_capture()
    handle.uninstall_capture()

    assert ran == ["third", "second", "first"]
    assert teardowns == []


@pytest.mark.needs_sqlalchemy
@pytest.mark.skipif(importlib.util.find_spec("sqlalchemy") is None, reason="needs SQLAlchemy")
def test_connection_listener_slot_attaches_and_removes() -> None:
    import sqlalchemy as sa

    from sharpit.engine import sqla

    engine = sa.create_engine("sqlite://")
    calls: list[str] = []

    def on_begin(conn: Any) -> None:
        calls.append("begin")

    assert sa.event.contains(sa.engine.Engine, "begin", on_begin) is False
    remove = sqla.add_connection_listener("begin", on_begin)
    with engine.begin() as conn:
        conn.execute(sa.text("select 1"))
    remove()
    remove()
    with engine.begin() as conn:
        conn.execute(sa.text("select 1"))

    assert calls == ["begin"]
    assert sa.event.contains(sa.engine.Engine, "begin", on_begin) is False


def test_connection_listener_slot_rejects_unknown_event() -> None:
    from sharpit.engine import sqla

    try:
        sqla.add_connection_listener("execute", lambda *_: None)  # pyright: ignore[reportArgumentType]
    except ValueError as exc:
        message: str | None = str(exc)
    else:
        message = None
    assert message == "unknown connection event 'execute'"


REPORT_ONLY_ARGS = ["--sharpit-report-only", "--sharpit-baseline", "baseline.json", "--sharpit-write-baseline"]


@pytest.mark.parametrize("failing", [False, True], ids=["passing", "failing"])
def test_report_only_options_are_accepted_and_inert(pytester: pytest.Pytester, failing: bool) -> None:
    pytester.makepyfile(f"def test_one(): assert {not failing}")
    plain = pytester.runpytest("-q", "-p", "no:cacheprovider")
    with_options = pytester.runpytest("-q", "-p", "no:cacheprovider", *REPORT_ONLY_ARGS)
    assert with_options.ret == plain.ret
    assert not (pytester.path / "baseline.json").exists()
