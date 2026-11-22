from __future__ import annotations

import asyncio
import json
import threading

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.console import (
    ActionAuditEvent,
    Console,
    ConsoleCall,
    ConsoleRequest,
    ConsoleResponse,
    RouteSpec,
)
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
        (((b"sec-fetch-site", b"same-origin"), (b"sec-fetch-site", b"cross-site")), MESSAGE_CROSS_SITE),
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

    adapter_sec_headers = {
        k.lower(): v
        for k, v in adapter_response.headers.items()
        if k.lower() in {name.lower() for name, _ in security_headers("api")}
    }
    console_sec_headers = {
        k.lower(): v for k, v in response.headers if k.lower() in {name.lower() for name, _ in security_headers("api")}
    }
    assert console_sec_headers == adapter_sec_headers


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


def test_action_route_calls_audit_hook_and_read_route_does_not(no_side_effects) -> None:
    no_side_effects.unblock_network()
    ctx = _context(no_side_effects)
    events: list[ActionAuditEvent] = []

    class RecordingHook:
        def on_action(self, event: ActionAuditEvent) -> None:
            events.append(event)

    action_route = RouteSpec(
        "test.action",
        "POST",
        "/api/custom/action",
        lambda _call: ConsoleResponse(200, (), b"ok"),
        "test-panel",
        "action",
    )
    read_route = RouteSpec(
        "test.read",
        "GET",
        "/api/custom/read",
        lambda _call: ConsoleResponse(200, (), b"ok"),
        "test-panel",
        "read",
    )
    mcp_route = RouteSpec(
        "mcp.rpc",
        "POST",
        "/api/mcp",
        lambda _call: ConsoleResponse(200, (), b"ok"),
        None,
        "action",
    )
    cli_route = RouteSpec(
        "cli.invoke",
        "POST",
        "/api/cli/tools/test",
        lambda _call: ConsoleResponse(200, (), b"ok"),
        None,
        "action",
    )
    console = Console(
        ctx,
        (action_route, read_route, mcp_route, cli_route),
        audit_hook=RecordingHook(),
    )

    response = asyncio.run(console.handle(_request("/api/custom/action", method="POST")))
    assert response.status == 200
    assert len(events) == 1
    event = events[0]
    assert event.action_id == "test.action"
    assert event.channel == "console"
    assert event.panel == "test-panel"
    assert event.status == 200
    assert event.ok is True
    assert event.timestamp_ms > 0

    read_response = asyncio.run(console.handle(_request("/api/custom/read", method="GET")))
    assert read_response.status == 200
    assert len(events) == 1

    mcp_response = asyncio.run(console.handle(_request("/api/mcp", method="POST")))
    assert mcp_response.status == 200
    assert len(events) == 1

    cli_response = asyncio.run(console.handle(_request("/api/cli/tools/test", method="POST")))
    assert cli_response.status == 200
    assert len(events) == 1


def test_sync_handler_runs_on_executor_unless_on_loop(no_side_effects) -> None:
    no_side_effects.unblock_network()
    ctx = _context(no_side_effects)
    loop_thread: threading.Thread | None = None
    sync_thread: threading.Thread | None = None
    on_loop_thread: threading.Thread | None = None

    def sync_handler(_call: ConsoleCall) -> ConsoleResponse:
        nonlocal sync_thread
        sync_thread = threading.current_thread()
        return ConsoleResponse(200, (), b"sync")

    def on_loop_handler(_call: ConsoleCall) -> ConsoleResponse:
        nonlocal on_loop_thread
        on_loop_thread = threading.current_thread()
        return ConsoleResponse(200, (), b"on_loop")

    routes = (
        RouteSpec("test.sync", "GET", "/api/test/sync", sync_handler, None, "read", on_loop=False),
        RouteSpec("test.on_loop", "GET", "/api/test/on_loop", on_loop_handler, None, "read", on_loop=True),
    )
    console = Console(ctx, routes)

    async def run_calls() -> None:
        nonlocal loop_thread
        loop_thread = threading.current_thread()
        await console.handle(_request("/api/test/sync"))
        await console.handle(_request("/api/test/on_loop"))

    asyncio.run(run_calls())

    assert sync_thread is not None
    assert loop_thread is not None
    assert sync_thread != loop_thread
    assert on_loop_thread is not None
    assert on_loop_thread == loop_thread


def test_query_parsing_keeps_blank_values(no_side_effects) -> None:
    no_side_effects.unblock_network()
    ctx = _context(no_side_effects)
    received_query: dict[str, str] = {}

    def handler(call: ConsoleCall) -> ConsoleResponse:
        received_query.update(call.query_params)
        return ConsoleResponse(200, (), b"ok")

    route = RouteSpec("test.query", "GET", "/api/test/query", handler, None, "read")
    console = Console(ctx, (route,))
    req = ConsoleRequest(
        "GET",
        "/api/test/query",
        "",
        b"offset=&limit=10",
        ((b"host", b"localhost"),),
        lambda _cap: b"",
        "http",
        "127.0.0.1",
        None,
        False,
    )
    response = asyncio.run(console.handle(req))
    assert response.status == 200
    assert received_query.get("offset") == ""
    assert received_query.get("limit") == "10"


def test_401_guard_denial_does_not_duplicate_cache_control(no_side_effects) -> None:
    no_side_effects.unblock_network()
    ctx = _context(no_side_effects, authentication_token="secret", allow_non_localhost=True)
    console = Console(ctx)
    req = ConsoleRequest(
        "GET",
        "/api/overview",
        "",
        b"",
        ((b"host", b"localhost"),),
        lambda _cap: b"",
        "http",
        "192.168.1.100",
        None,
        False,
    )
    response = asyncio.run(console.handle(req))
    assert response.status == 401
    cache_controls = [v for k, v in response.headers if k.lower() == "cache-control"]
    assert len(cache_controls) == 1
    keys = [k.lower() for k, _ in response.headers]
    assert len(keys) == len(set(keys))


def test_response_headers_keeps_other_headers_when_csp_set(no_side_effects) -> None:
    no_side_effects.unblock_network()
    ctx = _context(no_side_effects)

    def handler(_call: ConsoleCall) -> ConsoleResponse:
        return ConsoleResponse(200, (("Content-Security-Policy", "default-src 'none'"),), b"ok")

    route = RouteSpec("test.csp", "GET", "/api/test/csp", handler, None, "read")
    console = Console(ctx, (route,))
    response = asyncio.run(console.handle(_request("/api/test/csp")))
    assert response.status == 200
    header_dict = {k.lower(): v for k, v in response.headers}
    assert header_dict.get("content-security-policy") == "default-src 'none'"
    assert "x-frame-options" in header_dict
    assert "x-content-type-options" in header_dict


def test_joined_sec_fetch_site_denial_is_stricter_than_adapter_today(no_side_effects) -> None:
    """Console contract joined Sec-Fetch-Site denial is stricter than the adapter today.

    The design specifies that joined Sec-Fetch-Site is denied as cross-site (403),
    whereas the FastAPI adapter today does not reject comma-joined Sec-Fetch-Site and returns 200.
    """
    no_side_effects.unblock_network()
    ctx = _context(no_side_effects)
    headers = ((b"sec-fetch-site", b"same-origin,cross-site"),)
    response = asyncio.run(Console(ctx).handle(_request(headers=headers)))
    assert response.status == 403
    assert _json(response)["error"] == MESSAGE_CROSS_SITE

    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False)
    wire_headers = [(key.decode("latin-1"), value.decode("latin-1")) for key, value in headers]
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        adapter_response = client.get("/sharpit/api/overview", headers=wire_headers)

    assert adapter_response.status_code == 200


def test_static_fallback_on_json_error(no_side_effects, monkeypatch: pytest.MonkeyPatch) -> None:
    no_side_effects.unblock_network()
    ctx = _context(no_side_effects)

    def fail(_call: ConsoleCall) -> ConsoleResponse:
        raise RuntimeError("boom")

    route = RouteSpec("test.fail", "GET", "/api/test/fail", fail, None, "read")
    console = Console(ctx, (route,))

    import json as json_mod

    orig_dumps = json_mod.dumps

    def exploding_dumps(obj, *args, **kwargs):
        if isinstance(obj, dict) and obj.get("error") == "Internal Server Error":
            raise ValueError("json encoding failure")
        return orig_dumps(obj, *args, **kwargs)

    monkeypatch.setattr(json_mod, "dumps", exploding_dumps)

    response = asyncio.run(console.handle(_request("/api/test/fail")))
    assert response.status == 500
    assert response.body == b'{"error":"Internal Server Error"}'
    assert response.headers == tuple(security_headers("api"))
