"""A recording urllib transport for the GitHub client: no socket is ever opened.

``FakeTransport`` is a urllib handler placed before urllib's own HTTP(S) handlers, so the client's real
``no_redirect_opener`` (and its redirect and error processing) runs while every request lands here instead of the
network. Routes are keyed by URL path (the query is ignored, like the JDK ``HttpServer`` contexts BootUI's tests use).
"""

from __future__ import annotations

import io
import json
import urllib.request
import urllib.response
from collections.abc import Callable
from email.message import Message
from typing import Any
from urllib.parse import urlsplit

from sharpit.engine.collectors.github.client import GitHubApiClient, no_redirect_opener
from sharpit.engine.collectors.github.detector import Repository
from sharpit.engine.collectors.github.token import Token
from sharpit.engine.masking import Masker
from sharpit.settings import SharpitSettings

Reply = tuple[int, bytes | str, dict[str, str]]
SCOPES = {"X-OAuth-Scopes": "repo, workflow"}


def ok(body: Any, headers: dict[str, str] | None = None) -> Reply:
    return 200, body if isinstance(body, str) else json.dumps(body), {**SCOPES, **(headers or {})}


class FakeTransport(urllib.request.BaseHandler):
    handler_order = 100  # before urllib's HTTPHandler/HTTPSHandler (500): nothing reaches a socket

    def __init__(self, routes: dict[str, Reply | Callable[[urllib.request.Request], Reply]]) -> None:
        self.routes = routes
        self.requests: list[urllib.request.Request] = []

    def https_open(self, req: urllib.request.Request) -> urllib.response.addinfourl:
        self.requests.append(req)
        reply = self.routes.get(urlsplit(req.full_url).path, (404, "{}", {}))
        status, body, headers = reply(req) if callable(reply) else reply
        message = Message()
        for name, value in headers.items():
            message[name] = value
        raw = body.encode() if isinstance(body, str) else body
        response = urllib.response.addinfourl(io.BytesIO(raw), message, req.full_url, status)
        response.msg = "fake"  # type: ignore[attr-defined]  # urllib's error processor reads it
        return response

    http_open = https_open

    def paths(self) -> list[str]:
        return [urlsplit(r.full_url).path for r in self.requests]


def repository(host: str = "github.com", api: str = "https://api.github.com/") -> Repository:
    return Repository(
        "jdubois", "boot-ui", "jdubois/boot-ui", host, api, "https://github.com/jdubois/boot-ui", "main", "main"
    )


def settings(**overrides: Any) -> SharpitSettings:
    return SharpitSettings(**{"github_request_timeout": 2.0, **overrides})


def masker(base: SharpitSettings | None = None) -> Masker:
    s = base or SharpitSettings()
    return Masker(s.expose_values, s.mask_secrets)


def client(
    routes: dict[str, Any], token: str | None = "local-token", **overrides: Any
) -> tuple[GitHubApiClient, FakeTransport]:
    transport = FakeTransport(routes)
    s = settings(**overrides)

    def tokens(_timeout: float) -> Token | None:
        return None if token is None else Token(token, "test-token")

    return GitHubApiClient(s, tokens, no_redirect_opener(transport), scrub=masker(s).mask_text), transport
