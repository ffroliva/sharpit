from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.advisors.retention import AdvisorViolationError
from sharpit.engine.capture.streams import StreamSlots
from sharpit.engine.console import (
    ActionAuditEvent,
    Console,
    ConsoleCall,
    ConsoleFile,
    ConsoleRequest,
    ConsoleResponse,
    ConsoleStream,
    RouteSpec,
    match_route,
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


@pytest.mark.parametrize(
    ("method", "path", "route_id", "params"),
    [
        pytest.param("GET", "/api/files/42/a/b", "nested", {"file_id": "42", "name": "a/b"}, id="path-parameter"),
        pytest.param("POST", "/api/files/42", "write", {"file_id": "42"}, id="method"),
        pytest.param("GET", "/api/files/42", "read", {"file_id": "42"}, id="first-match"),
    ],
)
def test_match_route(method: str, path: str, route_id: str, params: dict[str, str]) -> None:
    def handler(_call: ConsoleCall) -> ConsoleResponse:
        return ConsoleResponse(200)

    read = RouteSpec("read", "GET", "/api/files/{file_id}", handler, None, "read")
    write = RouteSpec("write", "POST", "/api/files/{file_id}", handler, None, "action")
    nested = RouteSpec("nested", "GET", "/api/files/{file_id}/{name:path}", handler, None, "read")
    fallback = RouteSpec("fallback", "GET", "/api/files/{name:path}", handler, None, "read")
    routes = (read, write, nested, fallback)

    expected = next(route for route in routes if route.id == route_id)
    assert match_route(routes, method, path) == (expected, params)


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
    assert "sharpit console request failed:" in caplog.text
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


def test_response_headers_preserves_only_handler_headers_when_csp_set(dispatch) -> None:
    headers = (("content-Security-policy", "default-src 'none'"), ("Cache-Control", "no-cache"))

    def handler(_call: ConsoleCall) -> ConsoleResponse:
        return ConsoleResponse(200, headers, b"ok")

    route = RouteSpec("test.csp", "GET", "/api/test/csp", handler, None, "read")
    response = dispatch((route,), _request("/api/test/csp"))

    assert response.headers == headers
    assert response.status == 200


def test_joined_sec_fetch_site_is_not_denied_before_the_guard(no_side_effects) -> None:
    """A single comma-joined Sec-Fetch-Site value is not a duplicate on ASGI (design 3.1: no ASGI comma rule).

    Today's FastAPI adapter lets it reach the guard, and the console must keep those bytes; comma splitting belongs to
    the WSGI adapter, where the server folds duplicates.
    """
    no_side_effects.unblock_network()
    ctx = _context(no_side_effects)
    headers = ((b"sec-fetch-site", b"same-origin,cross-site"),)
    response = asyncio.run(Console(ctx).handle(_request(headers=headers)))
    assert _json(response).get("error") != MESSAGE_CROSS_SITE

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
    assert response.headers == (("Content-Type", "application/json"), *security_headers("api"))


def test_route_spec_stream_defaults_to_false() -> None:
    route = RouteSpec("test.default", "GET", "/api/overview", lambda _: ConsoleResponse(200, ()), None, "read")

    assert getattr(route, "stream", None) is False


@pytest.fixture
def console_loop() -> Iterator[asyncio.AbstractEventLoop]:
    # Windows creates the loop's wake-up socket before the side-effect fixture blocks networking.
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture
def dispatch(console_loop: asyncio.AbstractEventLoop, no_side_effects):
    ctx = _context(no_side_effects, trust_container_gateway="OFF")

    def handle(routes: tuple[RouteSpec, ...], request: ConsoleRequest) -> ConsoleResponse:
        return console_loop.run_until_complete(Console(ctx, routes).handle(request))

    return handle


def test_method_not_allowed_on_known_path(dispatch) -> None:
    route = RouteSpec("test.read", "GET", "/api/overview", lambda _: ConsoleResponse(200, ()), None, "read")

    other = RouteSpec("test.other", "POST", "/api/other", lambda _: ConsoleResponse(200, ()), None, "action")

    response = dispatch((route, other), _request(method="POST"))

    assert response.status == 405
    assert _json(response) == {"error": "Method Not Allowed"}
    assert dict(response.headers).get("Allow") == "GET, HEAD"


def test_allow_lists_every_matching_method_in_contract_order(dispatch) -> None:
    def handler(_call: ConsoleCall) -> ConsoleResponse:
        return ConsoleResponse(200, ())

    routes = (
        RouteSpec("test.delete", "DELETE", "/api/items/{id}", handler, None, "action"),
        RouteSpec("test.post", "POST", "/api/items/42", handler, None, "action"),
        RouteSpec("test.get", "GET", "/api/items/{id}", handler, None, "read"),
        RouteSpec("test.stream", "GET", "/api/items/42", handler, None, "read", stream=True),
    )

    response = dispatch(routes, _request("/api/items/42", method="PATCH"))

    assert dict(response.headers).get("Allow") == "GET, HEAD, POST, DELETE"
    assert response.status == 405


def test_unknown_path_remains_not_found(dispatch) -> None:
    route = RouteSpec("test.read", "GET", "/api/overview", lambda _: ConsoleResponse(200, ()), None, "read")

    response = dispatch((route,), _request("/api/missing"))

    assert response.status == 404
    assert _json(response) == {"error": "Not Found"}
    assert "Allow" not in dict(response.headers)


@pytest.mark.parametrize(
    ("method", "with_sibling"),
    [("HEAD", False), ("HEAD", True), ("POST", True), ("DELETE", True)],
)
def test_marked_stream_allows_only_get_without_running_handlers(dispatch, method: str, with_sibling: bool) -> None:
    calls: list[str] = []

    def stream(_call: ConsoleCall) -> ConsoleResponse:
        calls.append("stream")
        return ConsoleResponse(200, ())

    def detail(_call: ConsoleCall) -> ConsoleResponse:
        calls.append("detail")
        return ConsoleResponse(200, ())

    path = "/api/exceptions/stream"
    route = RouteSpec("test.stream", "GET", path, stream, None, "read", stream=True)
    sibling = RouteSpec("test.detail", "GET", "/api/exceptions/{id}", detail, None, "read")
    routes = (route, sibling) if with_sibling else (route,)

    response = dispatch(routes, _request(path, method=method))

    assert response.status == 405
    assert dict(response.headers).get("Allow") == "GET"
    assert calls == []


def test_head_preserves_get_status_and_headers_and_uses_byte_length(dispatch) -> None:
    body = "café".encode()
    route = RouteSpec(
        "test.read",
        "GET",
        "/api/items/{id}",
        lambda call: ConsoleResponse(202, (("X-Item", call.path_params["id"]),), body),
        None,
        "read",
    )
    get_response = dispatch((route,), _request("/api/items/42"))

    response = dispatch((route,), _request("/api/items/42", method="HEAD"))

    assert response.status == 202
    assert response.status == get_response.status
    assert dict(response.headers) == {**dict(get_response.headers), "Content-Length": str(len(body))}
    assert response.body == b""


def test_head_keeps_handler_content_length(dispatch) -> None:
    headers = (("content-length", "42"),)
    route = RouteSpec(
        "test.read", "GET", "/api/overview", lambda _: ConsoleResponse(200, headers, b"short"), None, "read"
    )

    response = dispatch((route,), _request(method="HEAD"))

    assert response.status == 200
    assert response.headers == (*headers, *security_headers("api"))
    assert response.body == b""


@pytest.mark.parametrize("status", [204, 304])
def test_head_does_not_infer_length_for_bodyless_status(dispatch, status: int) -> None:
    route = RouteSpec(
        "test.read", "GET", "/api/overview", lambda _: ConsoleResponse(status, (), b"ignored"), None, "read"
    )

    response = dispatch((route,), _request(method="HEAD"))

    assert response.status == status
    assert "Content-Length" not in dict(response.headers)
    assert response.body == b""


def test_head_preserves_file_for_the_adapter(dispatch, tmp_path: Path) -> None:
    file = ConsoleFile(tmp_path / "asset.txt")
    route = RouteSpec("test.asset", "GET", "/api/overview", lambda _: ConsoleResponse(200, (), file=file), None, "read")
    get_response = dispatch((route,), _request())

    response = dispatch((route,), _request(method="HEAD"))

    assert response.status == 200
    assert response == get_response


def test_head_keeps_handler_exception_response(dispatch) -> None:
    def handler(_call: ConsoleCall) -> ConsoleResponse:
        raise BadRequest("bad page")

    route = RouteSpec("test.read", "GET", "/api/overview", handler, None, "read")
    get_response = dispatch((route,), _request())

    response = dispatch((route,), _request(method="HEAD"))

    assert response.status == 400
    assert response == get_response
    assert _json(response) == {"error": "bad page"}


@pytest.mark.parametrize(("close_fails", "status"), [(False, 405), (True, 500)], ids=["close", "close-error"])
def test_head_closes_unmarked_stream_and_releases_slot(dispatch, close_fails: bool, status: int) -> None:
    slots = StreamSlots()
    acquired: list[int] = []
    closed: list[int] = []

    async def events() -> AsyncIterator[tuple[str, str | None, str]]:
        yield "unused", None, ""

    def on_close() -> None:
        closed.append(slots.count)
        if close_fails:
            raise RuntimeError("stream close failed")

    def handler(_call: ConsoleCall) -> ConsoleResponse:
        slots.acquire()
        acquired.append(slots.count)
        return ConsoleResponse(200, (), stream=ConsoleStream(events(), slots, 1, on_close))

    route = RouteSpec("test.unmarked", "GET", "/api/overview", handler, None, "read")

    response = dispatch((route,), _request(method="HEAD"))

    assert response.status == status
    assert acquired == [1]
    assert closed == [0]
    assert slots.count == 0
    if close_fails:
        assert _json(response) == {"error": "Internal Server Error"}
    else:
        assert dict(response.headers).get("Allow") == "GET"


@pytest.mark.parametrize("method", ["POST", "HEAD"])
def test_guard_denial_precedes_method_selection(dispatch, method: str) -> None:
    route = RouteSpec(
        "test.stream", "GET", "/api/overview", lambda _: ConsoleResponse(200, ()), None, "read", stream=True
    )
    headers = ((b"host", b"evil.example"),)

    response = dispatch((route,), _request(method=method, headers=headers))

    assert response.status == 403
    assert _json(response) == {"error": MESSAGE_DISALLOWED_HOST}
    assert dict(security_headers("api")).items() <= dict(response.headers).items()
    assert "Allow" not in dict(response.headers)


def test_advisor_violation_keeps_its_status_and_message(dispatch) -> None:
    def handler(_call: ConsoleCall) -> ConsoleResponse:
        raise AdvisorViolationError(422, "Invalid advisor violation")

    route = RouteSpec("test.advisor", "GET", "/api/overview", handler, None, "read")

    response = dispatch((route,), _request())

    assert response.status == 422
    assert _json(response) == {"error": "Invalid advisor violation"}


@pytest.mark.parametrize(
    ("method", "path", "is_probe", "status", "body"),
    [
        pytest.param("GET", "/api/missing", False, 404, b'{"error":"Not Found"}', id="not-found"),
        pytest.param("POST", "/api/overview", False, 405, b'{"error":"Method Not Allowed"}', id="wrong-method"),
        pytest.param("GET", "/api/bad", False, 400, b'{"error":"bad page"}', id="bad-request"),
        pytest.param("GET", "/api/fail", False, 500, b'{"error":"Internal Server Error"}', id="internal-error"),
        pytest.param(
            "GET",
            "/api/overview",
            True,
            403,
            b'{"error":"sharpit refused an internal probe request."}',
            id="denial",
        ),
    ],
)
def test_core_errors_are_compact_json(
    dispatch, method: str, path: str, is_probe: bool, status: int, body: bytes
) -> None:
    def bad_request(_call: ConsoleCall) -> ConsoleResponse:
        raise BadRequest("bad page")

    def fail(_call: ConsoleCall) -> ConsoleResponse:
        raise RuntimeError("handler failed")

    routes = (
        RouteSpec("test.read", "GET", "/api/overview", lambda _: ConsoleResponse(200, ()), None, "read"),
        RouteSpec("test.bad", "GET", "/api/bad", bad_request, None, "read"),
        RouteSpec("test.fail", "GET", "/api/fail", fail, None, "read"),
    )

    response = dispatch(routes, _request(path, method=method, is_probe=is_probe))

    assert response.body == body
    assert response.status == status
    assert dict(response.headers).get("Content-Type") == "application/json"


def test_core_error_content_type_is_application_json(dispatch) -> None:
    response = dispatch((), _request())

    assert dict(response.headers).get("Content-Type") == "application/json"


def test_core_error_encodes_non_ascii_message_as_utf8(dispatch) -> None:
    def handler(_call: ConsoleCall) -> ConsoleResponse:
        raise BadRequest("café")

    route = RouteSpec("test.bad", "GET", "/api/overview", handler, None, "read")

    response = dispatch((route,), _request())

    assert response.body == b'{"error":"caf\xc3\xa9"}'
