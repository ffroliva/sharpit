from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.console import Console, ConsoleCall, ConsoleRequest, ConsoleResponse, RouteSpec
from sharpit.engine.guard import MESSAGE_CROSS_SITE, MESSAGE_DISALLOWED_HOST
from sharpit.engine.headers import security_headers
from sharpit.engine.paging import BadRequest


def _request(
    path: str = "/api/overview",
    *,
    method: str = "GET",
    headers: tuple[tuple[bytes, bytes], ...] = ((b"host", b"localhost"),),
    is_probe: bool = False,
) -> ConsoleRequest:
    return ConsoleRequest(method, path, "", b"", headers, lambda _cap: b"", "http", "127.0.0.1", None, is_probe)


def _context(no_side_effects, **options):
    app = FastAPI()
    return install(app, enabled="ON", show_banner=False, config_scan=False, **options).context


def _json(response: ConsoleResponse) -> object:
    return json.loads(response.body or b"")


def test_unknown_path_under_disabled_panel_is_forbidden(no_side_effects) -> None:
    no_side_effects.unblock_network()
    ctx = _context(no_side_effects, panels={"sql-trace": {"enabled": False}})
    console = Console(ctx)

    response = asyncio.run(console.handle(_request("/api/sql-trace/missing")))

    assert response.status == 403
    assert _json(response)["error"] == "sharpit panel access denied"


@pytest.mark.parametrize(
    ("headers", "error"),
    [
        (((b"host", b"localhost"), (b"host", b"evil.example")), MESSAGE_DISALLOWED_HOST),
        (((b"origin", b"http://localhost"), (b"origin", b"http://evil.example")), MESSAGE_CROSS_SITE),
        (((b"host", b"localhost,evil.example"),), MESSAGE_DISALLOWED_HOST),
        (((b"origin", b"http://localhost,http://evil.example"),), MESSAGE_CROSS_SITE),
    ],
)
def test_duplicate_and_joined_headers_match_adapter_status_and_body(
    no_side_effects, headers: tuple[tuple[bytes, bytes], ...], error: str
) -> None:
    no_side_effects.unblock_network()
    ctx = _context(no_side_effects)
    response = asyncio.run(Console(ctx).handle(_request(headers=headers)))
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False)
    wire_headers = [(key.decode("latin-1"), value.decode("latin-1")) for key, value in headers]
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        adapter_response = client.get("/sharpit/api/overview", headers=wire_headers)

    assert response.status == adapter_response.status_code
    assert _json(response) == adapter_response.json()
    assert _json(response)["error"] == error


def test_post_route_marked_read_is_still_write_gated(no_side_effects) -> None:
    no_side_effects.unblock_network()
    ctx = _context(no_side_effects, panels={"loggers": {"read_only": True}})
    invoked = False

    def handler(_call: ConsoleCall) -> ConsoleResponse:
        nonlocal invoked
        invoked = True
        return ConsoleResponse(200, (), b"ok")

    route = RouteSpec("test.write", "POST", "/api/loggers/root", handler, "loggers", "read")
    response = asyncio.run(Console(ctx, (route,)).handle(_request("/api/loggers/root", method="POST")))

    assert response.status == 403
    assert invoked is False


def test_handler_exception_is_masked_and_bad_request_is_400(no_side_effects, caplog: pytest.LogCaptureFixture) -> None:
    no_side_effects.unblock_network()
    ctx = _context(no_side_effects)

    def fail(_call: ConsoleCall) -> ConsoleResponse:
        raise RuntimeError("password=secret-value Traceback in private")

    route = RouteSpec("test.fail", "GET", "/api/overview", fail, None, "read")
    response = asyncio.run(Console(ctx, (route,)).handle(_request()))
    body = response.body.decode()
    names = {key.lower() for key, _ in response.headers}

    assert response.status == 500
    assert "secret-value" not in body
    assert "Traceback" not in body
    assert "secret-value" not in caplog.text
    assert "content-security-policy" in names
    assert "x-frame-options" in names

    def bad(_call: ConsoleCall) -> ConsoleResponse:
        raise BadRequest("bad page")

    response = asyncio.run(
        Console(ctx, (RouteSpec("test.bad", "GET", "/api/overview", bad, None, "read"),)).handle(_request())
    )

    assert response.status == 400
    assert _json(response)["error"] == "bad page"


@pytest.mark.parametrize("response_class", ["api", "shell", "asset"])
def test_route_response_headers_match_response_class(no_side_effects, response_class: str) -> None:
    no_side_effects.unblock_network()
    ctx = _context(no_side_effects)
    route = RouteSpec(
        "test.headers",
        "GET",
        "/api/overview",
        lambda _call: ConsoleResponse(200, (), b"ok"),
        None,
        "read",
        response_class,
    )  # type: ignore[arg-type]

    response = asyncio.run(Console(ctx, (route,)).handle(_request()))

    assert response.headers == tuple(security_headers(response_class))


def test_internal_probe_request_is_refused(no_side_effects) -> None:
    no_side_effects.unblock_network()
    response = asyncio.run(Console(_context(no_side_effects)).handle(_request(is_probe=True)))

    assert response.status == 403
    assert _json(response)["error"] == "sharpit refused an internal probe request."
