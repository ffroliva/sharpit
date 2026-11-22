"""Expose the recorded request id on eligible application responses."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from starlette.types import Message, Scope

from sharpit.engine import guard
from sharpit.engine.capture.correlation import RequestInfo

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

HEADER = b"x-sharpit-request-id"


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
    # every header name goes to the guard, which owns the forwarding-header list
    header_names = {name.decode("latin-1").lower(): "" for name, _ in scope.get("headers", ())}
    facts = guard.RequestFacts(
        scope["method"],
        client[0] if client else None,
        header_names,
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
