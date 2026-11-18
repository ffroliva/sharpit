"""HTTP transport tests for the CLI client."""

from __future__ import annotations

import json
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

    with pytest.raises(ClientError) as unreachable:
        Client(options("http://127.0.0.1:1", token=secret)).get("/probe")
    messages.append(str(unreachable.value))

    assert messages == [
        f"No response from {base} within 1s. Raise --timeout if the tool is expected to be slow.",
        "Cannot reach sharpit at http://127.0.0.1:1. Is the application running, and is that the right --url?",
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
