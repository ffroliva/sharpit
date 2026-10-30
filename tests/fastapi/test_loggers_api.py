import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install

LOCAL = ("127.0.0.1", 50000)


def _client(**options: Any) -> TestClient:
    app = FastAPI()
    install(app, **{"enabled": "ON", "show_banner": False, **options})
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


@pytest.fixture
def restore_levels() -> Iterator[None]:
    saved = {n: lg.level for n, lg in logging.root.manager.loggerDict.items() if isinstance(lg, logging.Logger)}
    root = logging.root.level
    yield
    for name, lg in logging.root.manager.loggerDict.items():
        if isinstance(lg, logging.Logger):
            lg.setLevel(saved.get(name, logging.NOTSET))
    logging.root.setLevel(root)


def test_get_loggers_paged(no_side_effects: SideEffectGuard):
    no_side_effects.unblock_network()  # the Windows Proactor loop TestClient starts connects a self-pipe socketpair
    logging.getLogger("api.pg.one")
    logging.getLogger("api.pg.two")
    resp = _client().get("/sharpit/api/loggers", params={"q": "api.pg", "offset": 1, "limit": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert [lg["name"] for lg in body["loggers"]] == ["api.pg.two"]
    assert body["page"]["matched"] == 2 and body["availableLevels"][-1] == "NOTSET"


def test_get_loggers_bad_param_400(no_side_effects: SideEffectGuard):
    no_side_effects.unblock_network()
    resp = _client().get("/sharpit/api/loggers", params={"limit": "x"})
    assert resp.status_code == 400
    assert resp.json() == {"error": "Invalid 'limit' parameter"}


def test_post_sets_level(restore_levels: None):
    resp = _client().post("/sharpit/api/loggers/api.set", json={"level": "DEBUG"})
    assert resp.status_code == 200
    assert resp.json() == {"name": "api.set", "configuredLevel": "DEBUG", "effectiveLevel": "DEBUG"}
    assert logging.getLogger("api.set").level == logging.DEBUG


def test_post_null_level_resets(restore_levels: None):
    logging.getLogger("api.reset").setLevel(logging.DEBUG)
    resp = _client().post("/sharpit/api/loggers/api.reset", json={"level": None})
    assert resp.json()["configuredLevel"] is None


def test_post_unknown_level_and_own_logger_400(restore_levels: None):
    client = _client()
    bad = client.post("/sharpit/api/loggers/api.set", json={"level": "LOUD"})
    assert (bad.status_code, bad.json()) == (400, {"error": "Unknown level 'LOUD'"})
    own = client.post("/sharpit/api/loggers/sharpit.engine", json={"level": "DEBUG"})
    assert own.status_code == 400
    assert own.json() == {"error": "Refusing to change the level of sharpit's own logger 'sharpit.engine'."}


@pytest.mark.parametrize("raw", [b"not json", b"[1]", b'{"level": 5}'])
def test_post_malformed_body_400(restore_levels: None, raw: bytes):
    resp = _client().post("/sharpit/api/loggers/api.set", content=raw, headers={"content-type": "application/json"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_dotted_and_slash_names_route(restore_levels: None):
    client = _client()
    dotted = client.post("/sharpit/api/loggers/a.b/c", json={"level": "INFO"})
    assert dotted.json()["name"] == "a.b/c"
    encoded = client.post("/sharpit/api/loggers/x%2Fy.z", json={"level": "ERROR"})
    assert encoded.json()["name"] == "x/y.z"
    assert logging.getLogger("a.b/c").level == logging.INFO


def test_read_only_panel_403_on_post(restore_levels: None):
    client = _client(panels={"loggers": {"read_only": True}})
    resp = client.post("/sharpit/api/loggers/api.ro", json={"level": "DEBUG"})
    assert resp.status_code == 403
    assert resp.json()["panel"] == "loggers"
    assert "api.ro" not in logging.root.manager.loggerDict
    assert client.get("/sharpit/api/loggers").status_code == 200


def test_unknown_api_path_is_json_404():
    resp = _client().get("/sharpit/api/nope")
    assert resp.status_code == 404
    assert resp.json() == {"error": "Not Found"}
    assert resp.headers["content-type"].startswith("application/json")
    assert "content-security-policy" in resp.headers


def test_wrong_method_is_json_405_with_allow():
    resp = _client().options("/sharpit/api/overview")
    assert resp.status_code == 405
    assert resp.json() == {"error": "Method Not Allowed"}
    assert resp.headers["allow"] in ("GET, HEAD", "HEAD, GET")


@pytest.mark.parametrize(
    ("options", "pad"), [({}, 5000), ({"mcp_max_payload_bytes": 16}, 100)], ids=["default-cap", "mcp-cap"]
)
def test_logger_level_body_is_bounded(restore_levels: None, options: dict[str, Any], pad: int):
    # Task P1: the loggers write was the one unbounded body; it takes the small-body cap (never above the MCP cap)
    client = _client(**options)
    resp = client.post("/sharpit/api/loggers/capped.probe", json={"level": "DEBUG", "pad": "x" * pad})
    assert (resp.status_code, resp.json()) == (413, {"error": "Request payload exceeds limit"})
    assert logging.getLogger("capped.probe").level == logging.NOTSET
