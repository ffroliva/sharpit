"""HTTP transport tests for the CLI client."""

from __future__ import annotations

import json
import http.client
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from sharpit.cli.client import Client, ClientError


class Server(ThreadingHTTPServer):
    daemon_threads = True


@pytest.fixture
def endpoint():
    requests: list[tuple[str, str, str | None, bytes]] = []
    headers: list[dict[str, str]] = []
    routes: dict[str, tuple[int, bytes, str | None]] = {}
    delays: dict[str, float] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            size = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(size)
            requests.append((self.command, self.path, self.headers.get("Authorization"), body))
            headers.append(dict(self.headers.items()))
            status, payload, redirect = routes.get(self.path, (404, b"{}", None))
            if redirect:
                self.send_response(status)
                self.send_header("Location", redirect)
                self.end_headers()
                return
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            time.sleep(delays.get(self.path, 0))
            self.wfile.write(payload)

        def log_message(self, *_args):
            return

    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}", routes, requests, headers, delays
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def options(base: str, *, token: str | None = None, timeout: float = 1.0):
    return SimpleNamespace(base_url=base, api_path="/sharpit/api", token=token, timeout=timeout)


def test_client_reads_catalog_and_posts_only_the_supplied_arguments(endpoint):
    # ported: BootUiClientTests.readsTheCatalogFromTheCommandLineEndpoint
    # ported: BootUiClientTests.sendsOnlyTheArgumentsSuppliedSoUnusedOnesAreNotRejected
    base, routes, requests, *_ = endpoint
    routes["/sharpit/api/cli"] = (200, b'{"enabled":true,"tools":[]}', None)
    routes["/sharpit/api/cli/tools/example"] = (200, b'{"ok":true}', None)

    client = Client(options(base))

    assert client.catalog() == {"enabled": True, "tools": []}
    result = client.invoke("example", {"query": "abc", "limit": 2})
    assert getattr(result, "payload", None) == {"ok": True}
    assert requests[0][:2] == ("GET", "/sharpit/api/cli")
    assert requests[1][0:2] == ("POST", "/sharpit/api/cli/tools/example")
    assert json.loads(requests[1][3]) == {"query": "abc", "limit": 2}


def test_redirect_is_reported_without_following_or_resending_token(endpoint):
    # Scenario 1; BootUI has no dedicated redirect test.
    base, routes, requests, *_ = endpoint
    routes["/sharpit/api/probe"] = (302, b"", "http://127.0.0.1:1/elsewhere")
    client = Client(options(base, token="secret-token"))

    with pytest.raises(ClientError, match="redirect") as caught:
        client.get("/probe")

    assert len(requests) == 1
    assert requests[0][2] == "Bearer secret-token"
    assert "secret-token" not in str(caught.value)
    assert "secret-token" not in repr(caught.value)


def test_configured_proxy_is_ignored(monkeypatch, endpoint):
    # ported: BootUiClientTests.directClientBypassesConfiguredHttpProxy
    base, routes, requests, *_ = endpoint
    routes["/sharpit/api/probe"] = (200, b'{"direct":true}', None)
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")

    assert Client(options(base)).get("/probe") == {"direct": True}
    assert len(requests) == 1


@pytest.mark.parametrize("body", [b'{"key":1,"key":2}', b'{"oversized":"' + b"x" * 1_048_577 + b'"}'])
def test_duplicate_keys_and_oversized_bodies_are_rejected(endpoint, body):
    # ported: BootUiClientTests.boundedReadsRejectDuplicateKeysAndOversizedBodies
    base, routes, _, *_ = endpoint
    routes["/sharpit/api/probe"] = (200, body, None)

    with pytest.raises(ClientError):
        Client(options(base)).get("/probe")


def test_timeout_bounds_the_whole_body_read(endpoint):
    # ported: BootUiClientTests.boundedResponseBodyReadHonorsTheRemainingRequestTimeout
    base, routes, _, _, delays = endpoint
    routes["/sharpit/api/probe"] = (200, b'{"value":true}', None)
    delays["/sharpit/api/probe"] = 2.0
    started = time.monotonic()
    with pytest.raises(ClientError):
        Client(options(base, timeout=0.25)).get("/probe")
    assert time.monotonic() - started < 1.75


def test_token_header_is_conditional_and_never_appears_in_client_errors(endpoint):
    # ported: BootUiClientTests.sendsTheBearerTokenOnlyWhenOneIsConfigured
    base, routes, requests, headers, _ = endpoint
    routes["/sharpit/api/probe"] = (500, b"not json", None)
    routes["/sharpit/api/ok"] = (200, b'{"ok":true}', None)
    secret = "a-very-private-token"

    assert Client(options(base, token=secret)).get("/ok") == {"ok": True}
    with pytest.raises(ClientError) as caught:
        Client(options(base, token=secret)).get("/probe")
    assert Client(options(base)).get("/ok") == {"ok": True}
    for message in (str(caught.value), repr(caught.value)):
        assert secret not in message
    assert requests[0][2] == f"Bearer {secret}"
    assert requests[2][2] is None
    assert "Origin" not in headers[0]
    assert "Sec-Fetch-Site" not in headers[0]


def test_user_agent_names_sharpit_version(endpoint):
    base, routes, requests, headers, _ = endpoint
    routes["/sharpit/api/ok"] = (200, b"{}", None)

    Client(options(base)).get("/ok")

    assert len(requests) == 1
    from sharpit import __version__

    assert headers[0]["User-Agent"] == f"sharpit/{__version__}"


def test_empty_tool_arguments_are_sent_as_an_object(endpoint):
    # ported: BootUiClientTests.sendsAnEmptyObjectWhenATakesNoArguments
    base, routes, requests, *_ = endpoint
    routes["/sharpit/api/cli/tools/empty"] = (200, b"{}", None)

    result = Client(options(base)).invoke("empty", {})

    assert getattr(result, "payload", None) == {}
    assert requests[0][3] == b"{}"


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, b'{"ok":true}'),
        (400, b'{"error":"invalid"}'),
        (403, b'{"error":"refused"}'),
        (404, b'{"error":"missing"}'),
        (429, b'{"error":"busy"}'),
        (503, b'{"enabled":false}'),
        (504, b'{"error":"timeout"}'),
    ],
)
def test_invoke_returns_tool_name_status_and_json_for_every_http_status(endpoint, status, body):
    base, routes, *_ = endpoint
    routes["/sharpit/api/cli/tools/example"] = (status, body, None)
    result = None
    try:
        result = Client(options(base)).invoke("example", {})
    except ClientError:
        pass

    assert result is not None, "non-2xx tool answers must remain results"
    assert getattr(result, "tool_name", None) == "example"
    assert getattr(result, "status", None) == status
    assert getattr(result, "payload", None) == json.loads(body)


def test_get_uses_bootui_failure_description_with_panel_refusal_wording(endpoint):
    base, routes, *_ = endpoint
    routes["/sharpit/api/probe"] = (
        403,
        b'{"error":"BootUI panel access denied","panel":"config","reason":"Panel is read-only"}',
        None,
    )

    error = None
    try:
        Client(options(base)).get("/probe")
    except ClientError as caught:
        error = str(caught)

    assert error == "sharpit answered HTTP 403: sharpit panel access denied: Panel is read-only"


@pytest.mark.parametrize(
    ("status", "body", "detail"),
    [
        (400, b'{"error":"bad input","reason":"wrong type"}', ": bad input: wrong type"),
        (500, b'{"message":"server detail"}', ": server detail"),
        (500, b"not JSON", ""),
    ],
)
def test_get_describes_non_success_responses_without_exposing_raw_body(endpoint, status, body, detail):
    base, routes, *_ = endpoint
    routes["/sharpit/api/probe"] = (status, body, None)

    error = None
    try:
        Client(options(base)).get("/probe")
    except ClientError as caught:
        error = str(caught)

    assert error == f"sharpit answered HTTP {status}{detail}"


def test_catalog_404_names_the_missing_sharpit_endpoint_and_api_path(endpoint):
    base, routes, *_ = endpoint
    routes["/sharpit/api/cli"] = (404, b"{}", None)

    error = None
    try:
        Client(options(base)).catalog()
    except ClientError as caught:
        error = str(caught)

    assert error == (
        f"No sharpit command-line endpoint at {base}/sharpit/api/cli. The application may predate it, "
        "be running sharpit at a different --api-path, or not be a sharpit application."
    )


def test_invoke_rejects_non_json_with_the_endpoint_and_http_status(endpoint):
    base, routes, *_ = endpoint
    routes["/sharpit/api/cli/tools/example"] = (500, b"not JSON", None)

    error = None
    try:
        Client(options(base)).invoke("example", {})
    except ClientError as caught:
        error = str(caught)

    assert error == f"Response from {base}/sharpit/api/cli/tools/example does not contain JSON (HTTP 500)"


def test_client_transport_messages_match_bootui_and_redact_the_token(endpoint):
    base, routes, _, _, delays = endpoint
    secret = "message-secret"
    routes["/sharpit/api/probe"] = (200, b'{"ok":true}', None)
    delays["/sharpit/api/probe"] = 2.0
    messages = []

    with pytest.raises(ClientError) as timeout:
        Client(options(base, token=secret, timeout=1)).get("/probe")
    messages.append(str(timeout.value))

    closed = Server(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = closed.server_address[1]
    closed.server_close()
    with pytest.raises(ClientError) as unreachable:
        Client(options(f"http://127.0.0.1:{port}", token=secret)).get("/probe")
    messages.append(str(unreachable.value))

    assert messages == [
        f"No response from {base} within 1s. Raise --timeout if the tool is expected to be slow.",
        f"Cannot reach sharpit at http://127.0.0.1:{port}. Is the application running, and is that the right --url?",
    ]
    for message in messages:
        assert secret not in message
        assert f"Bearer {secret}" not in message


def test_bounded_calls_accept_the_callers_byte_cap_and_remaining_timeout(endpoint):
    base, routes, *_ = endpoint
    routes["/sharpit/api/cli/tools/example"] = (200, b'{"value":true}', None)
    assert hasattr(Client, "invoke_bounded"), "BootUI callers supply per-call response limits"

    result = Client(options(base)).invoke_bounded("example", {}, max_response_bytes=64, timeout=0.5)

    assert result.payload == {"value": True}


def _client_error_message(call):
    try:
        call()
    except ClientError as error:
        return str(error)
    return None


def test_bounded_timeout_uses_the_bootui_deadline_message(endpoint):
    base, routes, *_ = endpoint
    routes["/sharpit/api/cli/tools/slow"] = (200, b'{"ok":true}', None)
    endpoint[4]["/sharpit/api/cli/tools/slow"] = 2.0
    assert hasattr(Client, "invoke_bounded"), "bounded calls accept a remaining deadline"

    message = _client_error_message(
        lambda: Client(options(base)).invoke_bounded("slow", {}, max_response_bytes=64, timeout=0.25)
    )

    assert message == f"Request to {base} exceeded its response deadline."


def test_response_limit_message_uses_the_callers_byte_cap(endpoint):
    base, routes, *_ = endpoint
    routes["/sharpit/api/cli/tools/large"] = (200, b'{"ok":true}', None)
    assert hasattr(Client, "invoke_bounded"), "bounded calls accept a per-call byte cap"

    message = _client_error_message(
        lambda: Client(options(base)).invoke_bounded("large", {}, max_response_bytes=4)
    )

    assert message == "Response exceeded the 4 byte limit"


def test_invalid_utf8_has_the_bootui_message(endpoint):
    base, routes, *_ = endpoint
    routes["/sharpit/api/probe"] = (200, b"\xff", None)

    message = _client_error_message(lambda: Client(options(base, token="utf8-secret")).get("/probe"))

    assert message == "Response is not valid UTF-8"
    assert "utf8-secret" not in message
    assert "Bearer utf8-secret" not in message


def test_invalid_url_has_the_bootui_message(endpoint):
    message = _client_error_message(lambda: Client(options("not a url")).get("/probe"))

    assert message == "Not a valid URL: not a url/sharpit/api/probe"


def test_http_failure_message_uses_the_bootui_reason_without_the_token(endpoint):
    base, *_ = endpoint

    class FailedOpener:
        def open(self, *_args, **_kwargs):
            raise http.client.HTTPException("message-secret")

    client = Client(options(base, token="message-secret"))
    client._opener = FailedOpener()

    message = _client_error_message(lambda: client.get("/probe"))

    assert message == f"Request to {base} failed: [redacted]"
    assert "message-secret" not in message
    assert "Bearer message-secret" not in message


def test_bounded_read_works_when_response_has_no_private_socket():
    from sharpit.cli.client import _read_bounded

    class ResponseWithoutSocket:
        fp = SimpleNamespace(raw=SimpleNamespace())

        def __init__(self):
            self.chunks = [b'{"ok":true}', b""]

        def read1(self, _size):
            return self.chunks.pop(0)

    body = None
    try:
        body = _read_bounded(ResponseWithoutSocket(), time.monotonic() + 1)
    except AttributeError:
        pass

    assert body == b'{"ok":true}', "bounded response reads must not require response.fp.raw._sock"
