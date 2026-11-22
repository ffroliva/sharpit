"""A request carrying a client-address header is not a trusted source, whatever its peer."""

import pytest
from fastapi.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.guard import MESSAGE_FORWARDED_SOURCE

REMOTE = ("10.0.0.5", 50000)


class ClientFromHeader:
    """Sets the scope client to the address a header names, as a client-address middleware does."""

    def __init__(self, app: ASGIApp, header: bytes) -> None:
        self.app = app
        self.header = header

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            for name, value in scope["headers"]:
                if name == self.header:
                    scope["client"] = (value.decode(), 0)
        await self.app(scope, receive, send)


def _get(header: str | None) -> int:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    wrapped = ClientFromHeader(app, header.encode()) if header else app
    sent = {header: "127.0.0.1"} if header else {}
    client = TestClient(wrapped, base_url="http://localhost", client=REMOTE, follow_redirects=False)
    return client.get("/sharpit/api/overview", headers=sent).status_code


@pytest.mark.parametrize("header", ["cf-connecting-ip", "true-client-ip", "x-client-ip", "x-azure-clientip"])
def test_a_request_with_a_client_address_header_is_not_trusted(header: str) -> None:
    assert _get(header) == 403


def test_the_denial_names_the_forwarding_rule() -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    wrapped = ClientFromHeader(app, b"cf-connecting-ip")
    client = TestClient(wrapped, base_url="http://localhost", client=REMOTE, follow_redirects=False)
    resp = client.get("/sharpit/api/overview", headers={"CF-Connecting-IP": "127.0.0.1"})
    assert resp.json() == {"error": MESSAGE_FORWARDED_SOURCE}


def test_a_local_caller_without_the_header_is_still_trusted() -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000), follow_redirects=False)
    assert client.get("/sharpit/api/overview").status_code == 200
