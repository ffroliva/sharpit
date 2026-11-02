"""Secrets in span attributes never reach the ``traces`` bodies (lane A-traces; spec §6.1 item 3)."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import otel

STRIPE_KEY = "sk_live_4eC39HqLyjWDarjtT1zdp7dc"
BEARER = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
TRACE = 0xABCDEF0123456789ABCDEF0123456789


class Provider:
    def add_span_processor(self, processor: Any) -> None:
        pass


def test_secrets_in_span_attributes_never_appear(monkeypatch: pytest.MonkeyPatch):
    trace = ModuleType("opentelemetry.trace")
    provider = Provider()
    trace.get_tracer_provider = lambda: provider  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", ModuleType("opentelemetry.sdk.trace"))
    monkeypatch.setattr(otel, "PROCESSOR", otel.SharpitSpanProcessor())
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        otel.PROCESSOR.on_end(
            SimpleNamespace(
                context=SimpleNamespace(trace_id=TRACE, span_id=1),
                parent=None,
                name="POST /charge",
                kind=SimpleNamespace(name="SERVER"),
                resource=SimpleNamespace(attributes={"service.name": "api"}),
                instrumentation_scope=SimpleNamespace(name="tests"),
                start_time=1,
                end_time=2,
                status=SimpleNamespace(status_code=SimpleNamespace(name="ERROR"), description=f"key {STRIPE_KEY}"),
                attributes={
                    "url.full": "https://admin:hunter2@pay.example/charge?api_key=s3cr3tvalue",
                    "http.request.header.authorization": (BEARER,),
                    "db.statement": f"insert into charges values ('{STRIPE_KEY}')",
                },
                events=[],
            )
        )
        listed = client.get("/sharpit/api/traces").text
        detail = client.get(f"/sharpit/api/traces/{TRACE:032x}").text
    body = listed + detail
    assert '"spanCount":1' in listed
    assert STRIPE_KEY not in body
    assert "eyJhbGciOiJIUzI1NiJ9" not in body
    assert "hunter2" not in body
    assert "s3cr3tvalue" not in body
