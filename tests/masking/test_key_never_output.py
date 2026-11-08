"""The identity key is masked by value, in every exposure, as sharpit's own token is (ruling, plan item 9)."""

import logging
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

from engine.testsession.tsfakes import event
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.advisors.findings import AdvisorRun
from sharpit.engine.capture.securitylogs import MAX_VALUE_LENGTH, SecurityEventBuffer
from sharpit.engine.masking import MASK, Exposure, Masker
from sharpit.engine.spi import ApiModel
from sharpit.engine.testsession.sink import TestSessionSink
from sharpit.fastapi.adapter import SharpitMount
from sharpit.pytest_plugin import apps
from sharpit.settings import load_settings

KEY = "correct-horse-battery-staple-" + "identity-key"  # no secret's shape: only a match by value can catch it
RAW = KEY.encode()
TOKEN = "console-" + "token-of-the-test"
EXPOSURES = [(Exposure.MASKED, True), (Exposure.MASKED, False), (Exposure.FULL, True), (Exposure.FULL, False)]
OPTIONS: list[dict[str, Any]] = [
    {},
    {"mask_secrets": False},
    {"expose_values": "FULL"},
    {"expose_values": "FULL", "mask_secrets": False},
]
log = logging.getLogger("hostapp")


@pytest.mark.parametrize(("exposure", "mask_secrets"), EXPOSURES)
def test_a_value_holding_the_key_is_masked_whole(exposure: Exposure, mask_secrets: bool) -> None:
    masker = Masker(exposure, mask_secrets, identity_key=RAW)
    assert masker.mask("note", f"prefix {KEY}") == (MASK, True)


@pytest.mark.parametrize(("exposure", "mask_secrets"), EXPOSURES)
def test_text_holding_the_key_loses_it(exposure: Exposure, mask_secrets: bool) -> None:
    masker = Masker(exposure, mask_secrets, identity_key=RAW)
    assert masker.mask_text(f"line {KEY} end") == f"line {MASK} end"
    assert masker.mask_statement(f"select {KEY}") == f"select {MASK}"


@pytest.mark.parametrize(("exposure", "mask_secrets"), EXPOSURES)
def test_a_path_or_query_holding_the_key_loses_it(exposure: Exposure, mask_secrets: bool) -> None:
    masker = Masker(exposure, mask_secrets, identity_key=RAW)
    assert KEY not in masker.mask_path(f"/a/{KEY}/b")
    assert KEY not in str(masker.mask_query(f"note={KEY}"))
    assert KEY not in str(masker.mask_header("x-note", [KEY]))


@pytest.mark.parametrize(("exposure", "mask_secrets"), EXPOSURES)
def test_the_token_is_still_masked_beside_the_key(exposure: Exposure, mask_secrets: bool) -> None:
    masker = Masker(exposure, mask_secrets, TOKEN, identity_key=RAW)
    assert masker.mask_text(f"{TOKEN} {KEY}") == f"{MASK} {MASK}"


def test_a_key_set_after_the_masker_was_built_is_masked() -> None:
    masker = Masker(Exposure.FULL, False)
    masker.identity_key = RAW
    assert masker.mask("note", KEY) == (MASK, True)


def test_a_session_sink_masks_the_key_it_is_given() -> None:
    sink = TestSessionSink("main")
    sink.set_identity_key(RAW)
    sink.on_sql(event(f"SELECT {KEY} FROM jobs"), None)
    assert sink.facts.unattributed == 1
    assert KEY not in repr(sink.facts.top_unattributed)


def test_an_advisor_masks_with_the_sessions_key(monkeypatch: pytest.MonkeyPatch) -> None:
    sink = TestSessionSink("main")
    sink.set_identity_key(RAW)
    seen: list[Masker] = []

    def assess(_model: object, masker: Masker, **_options: Any) -> AdvisorRun:
        seen.append(masker)
        return AdvisorRun("rest-api", "UNKNOWN", (), {}, "seen", "app")

    monkeypatch.setattr(apps, "_models_to_assess", lambda *_args: [("app", ApiModel((), (), ()))])
    options = SimpleNamespace(advisors=True, app="app", fail_on="high")
    apps.run_advisors(SimpleNamespace(sink=sink, options=options, dismissed=set()), assess_fn=assess)
    assert seen != []
    assert seen[0].mask("note", KEY) == (MASK, True)


def test_a_key_that_is_no_text_gives_no_mask() -> None:
    """A file key is random bytes: no text carries it, and no stray mask comes of decoding part of it."""
    masker = Masker(Exposure.MASKED, False, identity_key=b"\xff" + b"a" * 31)
    assert masker.mask_text("a plain line") == "a plain line"


def test_a_long_security_event_keeps_no_part_of_the_key() -> None:
    """Strict masking runs before the cut: a key it does not know would be stored half, past any later match."""
    buffer = SecurityEventBuffer(5, masker=Masker(Exposure.MASKED, True, identity_key=RAW))
    buffer.add("login", None, {"note": "x" * (MAX_VALUE_LENGTH - 10) + KEY}, None)
    assert KEY[:10] not in repr(buffer.snapshot())


def test_the_settings_repr_shows_neither_secret() -> None:
    settings = load_settings({"authentication_token": TOKEN, "identity_key": KEY}, {})
    shown = repr(settings) + repr(replace(settings, read_only=True))
    assert KEY not in shown
    assert TOKEN not in shown


def _app(state_dir: str, **options: Any) -> FastAPI:
    app = FastAPI()

    @app.get("/boom")
    def boom() -> None:
        log.error("started with %s", KEY)
        raise RuntimeError(f"bad key {KEY}")

    @app.get("/echo/{part}")
    def echo(part: str) -> dict[str, str]:
        return {"part": part}

    install(
        app,
        enabled="ON",
        show_banner=False,
        state_dir=state_dir,
        mcp_enabled="ON",
        authentication_token=TOKEN,
        stream_max_seconds=0.05,
        **options,
    )
    return app


def _get_routes(app: FastAPI) -> list[str]:
    mount = next(route for route in app.router.routes if isinstance(route, SharpitMount))
    found = [route.path_format for route in mount.routes if isinstance(route, Route) and "GET" in (route.methods or ())]
    return ["/sharpit" + path for path in found if "{" not in path]


@pytest.mark.parametrize("options", OPTIONS, ids=repr)
def test_no_get_and_no_mcp_tool_shows_the_key(
    options: dict[str, Any], tmp_state_dir: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHARPIT_IDENTITY_KEY", KEY)
    monkeypatch.setenv("A_COPY_UNDER_ANOTHER_NAME", KEY)
    logging.getLogger("hostapp").addHandler(logging.NullHandler())
    app = _app(str(tmp_state_dir), **options)
    bearer = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(
        app, base_url="http://localhost", client=("127.0.0.1", 50000), raise_server_exceptions=False, headers=bearer
    ) as client:
        client.get("/boom")
        client.get(f"/echo/{KEY}", params={"note": KEY})
        seen = {path: client.get(path).text for path in _get_routes(app)}
        for tool in ("get_log_tail", "get_config"):
            call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": {}}}
            seen[tool] = client.post("/sharpit/api/mcp", json=call).text
    assert "bad key" in seen["/sharpit/api/exceptions"], "the sweep must have reached the exception"
    assert "A_COPY_UNDER_ANOTHER_NAME" in seen["/sharpit/api/config"], "the sweep must have reached the copy"
    assert "started with" in seen["/sharpit/api/log-tail/recent"], "the sweep must have reached the log line"
    assert [path for path, text in seen.items() if KEY in text] == []
