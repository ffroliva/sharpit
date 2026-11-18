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
    assert client.invoke("example", {"query": "abc", "limit": 2}) == {"ok": True}
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
    delays["/sharpit/api/probe"] = 0.8
    started = time.monotonic()
    with pytest.raises(ClientError):
        Client(options(base, timeout=0.25)).get("/probe")
    assert time.monotonic() - started < 0.7


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

    assert result == {}
    assert requests[0][3] == b"{}"
