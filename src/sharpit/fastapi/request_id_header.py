"""Expose the recorded request id on eligible application responses."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from starlette.types import Message, Scope

from sharpit.engine import guard
from sharpit.engine.capture.correlation import RequestInfo
from sharpit.engine.panels import panel_is_implemented

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

HEADER = b"x-sharpit-request-id"
_FORWARDED_HEADERS = (b"forwarded", b"x-forwarded-for", b"x-real-ip")


def with_request_id_header(ctx: SharpitContext, scope: Scope, message: Message, info: RequestInfo) -> Message:
    headers = cast("list[tuple[bytes, bytes]]", message["headers"])
    settings = ctx.settings
    if (
        not settings.http_exchanges_expose_request_id_header
        or not panel_is_implemented("http-exchanges")
        or not settings.panels["http-exchanges"].enabled
        or ctx.capture.exchanges is None
    ):
        return message

    if any(name.lower() == HEADER for name, _ in headers):
        return message

    client = scope.get("client")
    forwarded_headers = {
        name.decode("latin-1").lower(): ""
        for name, _ in cast("list[tuple[bytes, bytes]]", scope.get("headers", ()))
        if name.lower() in _FORWARDED_HEADERS
    }
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
