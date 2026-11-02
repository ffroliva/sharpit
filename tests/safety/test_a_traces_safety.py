"""``traces`` reads have no side effects and never attach the span processor (lane A-traces; safety model 4)."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest
from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from sharpit.engine import otel

PANEL = "traces"
GET_ROWS = ["/sharpit/api/traces", "/sharpit/api/traces/{id}"]
WRITE_ROWS = [("DELETE", "/sharpit/api/traces")]


class Provider:
    def __init__(self) -> None:
        self.processors: list[Any] = []

    def add_span_processor(self, processor: Any) -> None:
        self.processors.append(processor)


def test_get_no_side_effects(no_side_effects: SideEffectGuard, monkeypatch: pytest.MonkeyPatch):
    provider = Provider()
    trace = ModuleType("opentelemetry.trace")
    trace.get_tracer_provider = lambda: provider  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", ModuleType("opentelemetry.sdk.trace"))
    monkeypatch.setattr(otel, "PROCESSOR", otel.SharpitSpanProcessor())
    app = create_app(show_banner=False, state_dir=str(no_side_effects.state_dir), mcp_enabled="ON")
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        sinks = otel.PROCESSOR.sinks
        no_side_effects.block_network()
        listed = client.get("/sharpit/api/traces")
        detail = client.get("/sharpit/api/traces/0123456789abcdef")
    assert listed.status_code == 200
    assert detail.status_code == 404
    assert provider.processors == [otel.PROCESSOR]
    assert otel.PROCESSOR.sinks == sinks
    assert no_side_effects.violations == []
