"""The security-sinks matcher: joins request context, holder and an injected ownership port; builds sink rows."""

from __future__ import annotations

import contextvars
import functools
import time
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any, NoReturn, cast

import pytest

from sharpit.engine.capture import frames
from sharpit.engine.capture.correlation import INTERNAL, REQUEST, RequestInfo
from sharpit.engine.sensors.sinks import (
    F_BUSY,
    F_SEEN,
    Match,
    RequestValues,
    SecuritySinksSensor,
    SinkMatcher,
    keyed_hash,
    unchecked,
)
from sharpit.fastapi import sink_ownership


def info(
    query: str = "",
    path: dict[str, Any] | None = None,
    request_id: str = "a" * 16,
    context_id: str = "ctx",
) -> RequestInfo:
    scope: dict[str, Any] = {"query_string": query.encode(), **({"path_params": path} if path is not None else {})}
    return RequestInfo(request_id, context_id, "GET", "/", None, 0, None, scope=scope)


@pytest.fixture(autouse=True)
def clean_context() -> Iterator[None]:
    req_token = REQUEST.set(None)
    int_token = INTERNAL.set(False)
    try:
        yield
    finally:
        REQUEST.reset(req_token)
        INTERNAL.reset(int_token)


def test_one_row_per_matched_parameter() -> None:
    REQUEST.set(info("a=alpha&b=bravo"))
    matcher = SinkMatcher("ctx", on=lambda: True, owns=lambda scope: True)
    text = "alpha/bravo"
    match = matcher.check(text, "file")
    assert match is not None
    rows = matcher.rows("file", match, text, target="/srv/out")
    assert [r["parameter"] for r in rows] == ["a", "b"]
    assert "alpha" not in repr(rows)
    assert "bravo" not in repr(rows)
    assert rows[0]["source"] == "security-sinks"
    assert rows[0]["kind"] == "file-path"
    assert rows[0]["target"] == "/srv/out"
    assert rows[0]["requestId"] == "a" * 16
    assert rows[0]["numeric"] is False
    assert rows[0]["rawHash"] == keyed_hash(text)
    assert rows[0]["redactedHash"] == keyed_hash(match.redacted) if match.redacted is not None else 0


def test_no_row_for_work_the_endpoint_does_not_own() -> None:
    REQUEST.set(info("file=report-q3"))
    matcher = SinkMatcher("ctx", on=lambda: True, owns=lambda scope: False)
    text = "/srv/report-q3.pdf"
    match = matcher.check(text, "file")
    assert match is not None
    assert match.names == ("file",)
    assert matcher.rows("file", match, text, None) == ()


def test_a_text_seen_before_publishes_no_second_row() -> None:
    REQUEST.set(info("file=report-q3"))
    matcher = SinkMatcher("ctx", on=lambda: True, owns=lambda scope: True)
    text = "/srv/report-q3.pdf"
    match1 = matcher.check(text, "file")
    assert match1 is not None
    rows1 = matcher.rows("file", match1, text, None)
    assert len(rows1) == 1
    match2 = matcher.check(text, "file")
    assert match2 is not None
    assert bool(match2.flags & F_SEEN)
    assert match2.redacted == match1.redacted
    rows2 = matcher.rows("file", match2, text, None)
    assert rows2 == ()


@pytest.mark.parametrize("case", ["off", "internal", "no_request", "other_context"])
def test_nothing_is_checked_when_off_internal_outside_a_request_or_for_another_context(case: str) -> None:
    on = (lambda: False) if case == "off" else (lambda: True)
    if case == "internal":
        INTERNAL.set(True)
    if case == "other_context":
        REQUEST.set(info("file=report-q3", context_id="other"))
    elif case != "no_request":
        REQUEST.set(info("file=report-q3", context_id="ctx"))
    matcher = SinkMatcher("ctx", on=on, owns=lambda scope: True)
    assert matcher.check("/srv/report-q3.pdf", "file") is None


def test_a_digits_only_value_is_flagged() -> None:
    # ported: RequestValuesSinksTests.aDigitsOnlyValueIsFlaggedSoTheEngineWaitsForConfirmation
    REQUEST.set(info("year=2024"))
    matcher = SinkMatcher("ctx", on=lambda: True, owns=lambda scope: True)
    text = "/srv/archive/2024/data"
    match = matcher.check(text, "file")
    assert match is not None
    rows = matcher.rows("file", match, text, None)
    assert len(rows) == 1
    assert rows[0]["numeric"] is True
    assert rows[0]["parameter"] == "year"


def test_the_same_text_hashes_alike_and_another_value_differently() -> None:
    matcher = SinkMatcher("ctx", on=lambda: True, owns=lambda scope: True)

    REQUEST.set(info("file=report-a", request_id="1" * 16))
    text1 = "/srv/report-a.pdf"
    match1 = matcher.check(text1, "file")
    assert match1 is not None
    rows1 = matcher.rows("file", match1, text1, None)
    assert len(rows1) == 1

    REQUEST.set(info("file=report-b", request_id="2" * 16))
    text2 = "/srv/report-b.pdf"
    match2 = matcher.check(text2, "file")
    assert match2 is not None
    rows2 = matcher.rows("file", match2, text2, None)
    assert len(rows2) == 1

    assert rows1[0]["redactedHash"] == rows2[0]["redactedHash"]
    assert rows1[0]["rawHash"] != rows2[0]["rawHash"]
    assert rows1[0]["redactedHash"] != 0
    assert rows1[0]["rawHash"] != 0


def test_an_owns_that_raises_publishes_nothing() -> None:
    def bad_owns(scope: Mapping[str, Any]) -> bool:
        raise RuntimeError("boom")

    REQUEST.set(info("file=report-q3"))
    matcher = SinkMatcher("ctx", on=lambda: True, owns=bad_owns)
    text = "/srv/report-q3.pdf"
    match = matcher.check(text, "file")
    assert match is not None
    assert match.names == ("file",)
    assert matcher.rows("file", match, text, None) == ()


def test_work_not_owned_never_hides_the_endpoints_later_row() -> None:
    owned = False
    REQUEST.set(info("file=report-q3"))
    matcher = SinkMatcher("ctx", on=lambda: True, owns=lambda scope: owned)
    text = "/srv/report-q3.pdf"

    match1 = matcher.check(text, "file")
    assert match1 is not None
    rows1 = matcher.rows("file", match1, text, None)
    assert rows1 == ()

    owned = True
    match2 = matcher.check(text, "file")
    assert match2 is not None
    assert not (match2.flags & F_SEEN)
    rows2 = matcher.rows("file", match2, text, None)
    assert len(rows2) == 1
    assert rows2[0]["parameter"] == "file"


def test_a_holder_that_raises_gives_a_not_checked_match(monkeypatch: pytest.MonkeyPatch) -> None:
    values = RequestValues()

    def raise_match(*args: Any, **kwargs: Any) -> Match:
        raise RuntimeError("match exploded")

    monkeypatch.setattr(values, "match", raise_match)
    REQUEST.set(info("file=report-q3"))
    matcher = SinkMatcher("ctx", on=lambda: True, values=values, owns=lambda scope: True)
    text = "/srv/report-q3.pdf"
    match = matcher.check(text, "file")
    assert match is not None
    assert unchecked(match)
    assert bool(match.flags & F_BUSY)
    assert matcher.rows("file", match, text, None) == ()


def test_the_default_owns_publishes_nothing() -> None:
    REQUEST.set(info("file=report-q3"))
    matcher = SinkMatcher("ctx", on=lambda: True)
    sensor = SecuritySinksSensor(matcher)
    assert sensor.name == "security-sinks"
    assert sensor.events == ()
    assert sensor.record("any", ()) == ()
    sensor.wipe()
    text = "/srv/report-q3.pdf"
    match = matcher.check(text, "file")
    assert match is not None
    assert match.names == ("file",)
    assert matcher.rows("file", match, text, None) == ()


def test_position_unknown_past_eight_spans() -> None:
    REQUEST.set(info("a=aaaa&b=bbbb"))
    matcher = SinkMatcher("ctx", on=lambda: True, owner=lambda scope: "app:fn")
    text = "aaaa " * 8 + "bbbb"
    match = matcher.check(text, "file")
    assert match is not None
    rows = matcher.rows("file", match, text, target="/srv/out")
    by_param = {r["parameter"]: r["positionUnknown"] for r in rows}
    assert by_param["a"] is False
    assert by_param["b"] is True


def test_call_site_is_the_first_application_frame_without_a_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient
    from tests.fastapi.test_sink_ownership import open_sink_path

    from fastapi import FastAPI
    from sharpit import install
    from sharpit.engine.sensors import audit

    monkeypatch.setattr(audit.hub, "_add_hook", lambda _hook: None)
    monkeypatch.setattr(audit.hub, "_installed", False)
    app = FastAPI()
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        state_dir=str(tmp_path / "state"),
        agent_sensors=("files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )

    @app.get("/read/{name}")
    def read_path(name: str) -> str:
        open_sink_path(f"reports/{name}.csv")
        return name

    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            assert client.get("/read/quarterly").status_code == 200
    finally:
        handle.uninstall_capture()
        audit.hub.release()
    journal = handle.context.capture.journal
    assert journal is not None
    rows = journal.records("security-sinks")
    assert [r.get("callSite") for r in rows] == ["tests.fastapi.test_sink_ownership:open_sink_path"]


def test_the_call_site_comes_from_the_ownership_walk(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> NoReturn:
        raise AssertionError("first_application_frame was called")

    monkeypatch.setattr(frames, "first_application_frame", forbidden)

    def endpoint() -> tuple[Mapping[str, object], ...]:
        return matcher.rows("file", match, text, target="/srv/out")

    req = info("file=report-q3")
    assert req.scope is not None
    req.scope["endpoint"] = endpoint
    REQUEST.set(req)
    matcher = SinkMatcher("ctx", on=lambda: True, owner=sink_ownership.owner)
    text = "/srv/report-q3.pdf"
    match = matcher.check(text, "file")
    assert match is not None
    rows = endpoint()
    assert [r["callSite"] for r in rows] == [
        f"{__name__}:test_the_call_site_comes_from_the_ownership_walk.<locals>.endpoint"
    ]


def test_a_call_site_in_the_parent_greenlet_is_found_by_the_ownership_walk() -> None:
    greenlet = pytest.importorskip("greenlet")

    def helper(call: Callable[[], tuple[Mapping[str, object], ...]]) -> tuple[Mapping[str, object], ...]:
        child = greenlet.greenlet(call)
        child.gr_context = contextvars.copy_context()
        return cast("tuple[Mapping[str, object], ...]", child.switch())

    def endpoint(call: Callable[[], tuple[Mapping[str, object], ...]]) -> tuple[Mapping[str, object], ...]:
        return helper(call)

    req = info("file=report-q3")
    assert req.scope is not None
    req.scope["endpoint"] = endpoint
    REQUEST.set(req)
    matcher = SinkMatcher("ctx", on=lambda: True, owner=sink_ownership.owner)
    text = "/srv/report-q3.pdf"
    match = matcher.check(text, "file")
    assert match is not None
    rows = endpoint(functools.partial(matcher.rows, "file", match, text, "/srv/out"))
    assert [r["callSite"] for r in rows] == [
        f"{__name__}:test_a_call_site_in_the_parent_greenlet_is_found_by_the_ownership_walk.<locals>.helper"
    ]


def test_a_row_carries_its_epoch_millisecond_time() -> None:
    REQUEST.set(info("file=report-q3"))
    matcher = SinkMatcher("ctx", on=lambda: True, owner=lambda scope: "app:fn")
    text = "/srv/report-q3.pdf"
    match = matcher.check(text, "file")
    assert match is not None
    before = time.time_ns() // 1_000_000
    rows = matcher.rows("file", match, text, target="/srv/out")
    after = time.time_ns() // 1_000_000
    assert len(rows) == 1
    at = rows[0]["at"]
    assert isinstance(at, int)
    assert before <= at <= after


def test_not_owned_work_publishes_no_row_and_takes_no_call_site(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> NoReturn:
        raise AssertionError("first_application_frame was called")

    monkeypatch.setattr(frames, "first_application_frame", forbidden)
    REQUEST.set(info("file=report-q3"))
    matcher = SinkMatcher("ctx", on=lambda: True, owner=lambda scope: None)
    text = "/srv/report-q3.pdf"
    match = matcher.check(text, "file")
    assert match is not None
    assert matcher.rows("file", match, text, target="/srv/out") == ()
