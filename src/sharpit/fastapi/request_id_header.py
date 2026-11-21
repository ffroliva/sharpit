"""Expose the recorded request id on eligible application responses."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from starlette.types import Message, Scope

from sharpit.engine import guard
from sharpit.engine.capture.correlation import RequestInfo

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

HEADER = b"x-sharpit-request-id"
_FORWARDED_HEADERS = (b"forwarded", b"x-forwarded-for", b"x-real-ip")
_NO_FORWARDED_HEADERS: dict[str, str] = {}


def with_request_id_header(
    ctx: SharpitContext,
    scope: Scope,
    message: Message,
    info: RequestInfo,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Message:
    headers = headers if headers is not None else list(cast("list[tuple[bytes, bytes]]", message["headers"]))
    settings = ctx.settings
    if ctx.capture.exchanges is None:
        return message

    if any(name.lower() == HEADER for name, _ in headers):
        return message

    client = scope.get("client")
    forwarded_headers = _NO_FORWARDED_HEADERS
    for name, _ in cast("list[tuple[bytes, bytes]]", scope.get("headers", ())):
        lowered = name.lower()
        if lowered in _FORWARDED_HEADERS:
            if forwarded_headers is _NO_FORWARDED_HEADERS:
                forwarded_headers = {}
            forwarded_headers[lowered.decode("latin-1")] = ""
    facts = guard.RequestFacts(
        scope["method"],
        client[0] if client else None,
        forwarded_headers,
        None,
        scope.get("scheme", "http"),
    )
    gateway = (
        ctx.lazy("gateway", guard.detect_container_gateway)
        if settings.trust_container_gateway.upper() != "OFF"
        else None
    )
    if not guard.is_trusted_source(facts, settings, gateway):
        return message

    return {**message, "headers": [*headers, (HEADER, info.id.encode("ascii"))]}
