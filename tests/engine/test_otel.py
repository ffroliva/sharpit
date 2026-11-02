"""The OpenTelemetry gatekeeper (lane A-traces, spec §6.3): reads ``sys.modules``, never imports or installs OTel.

The SDK is not a test dependency, so these tests plant SDK-shaped modules in ``sys.modules``; the processor only
relies on the duck-typed ``add_span_processor`` / ``on_end`` contract.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from sharpit.engine import otel


class FakeSdkProvider:
    def __init__(self) -> None:
        self.processors: list[Any] = []

    def add_span_processor(self, processor: Any) -> None:
        self.processors.append(processor)


class ProxyProvider:  # the API's no-op default: no add_span_processor
    pass


class Sink:
    def __init__(self) -> None:
        self.spans: list[Any] = []

    def add(self, span: Any) -> None:
        self.spans.append(span)


class BrokenSink:
    def add(self, span: Any) -> None:
        raise RuntimeError("boom")


def plant(monkeypatch: pytest.MonkeyPatch, provider: Any, *, sdk: bool = True) -> None:
    trace = ModuleType("opentelemetry.trace")
    trace.get_tracer_provider = lambda: provider  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace)
    if sdk:
        monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", ModuleType("opentelemetry.sdk.trace"))
    else:
        monkeypatch.delitem(sys.modules, "opentelemetry.sdk.trace", raising=False)


@pytest.fixture(autouse=True)
def fresh_processor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(otel, "PROCESSOR", otel.SharpitSpanProcessor())


def test_no_sdk_is_unavailable(monkeypatch: pytest.MonkeyPatch):
    plant(monkeypatch, FakeSdkProvider(), sdk=False)
    assert otel.unavailable_reason() == "OpenTelemetry SDK is not imported by this application"
    assert otel.attach(Sink()) is None


def test_proxy_provider_is_unavailable(monkeypatch: pytest.MonkeyPatch):
    plant(monkeypatch, ProxyProvider())
    assert otel.unavailable_reason() == "The global tracer provider is not an SDK TracerProvider"
    assert otel.attach(Sink()) is None


def test_sdk_provider_is_available(monkeypatch: pytest.MonkeyPatch):
    plant(monkeypatch, FakeSdkProvider())
    assert otel.unavailable_reason() is None


def test_attach_adds_once(monkeypatch: pytest.MonkeyPatch):
    provider = FakeSdkProvider()
    plant(monkeypatch, provider)
    otel.attach(Sink())
    otel.attach(Sink())
    assert provider.processors == [otel.PROCESSOR]


def test_disarm_stops_delivery(monkeypatch: pytest.MonkeyPatch):
    plant(monkeypatch, FakeSdkProvider())
    sink = Sink()
    remover = otel.attach(sink)
    assert remover is not None
    otel.PROCESSOR.on_end("first")
    remover()
    otel.PROCESSOR.on_end("second")
    assert sink.spans == ["first"]


def test_on_end_raising_is_swallowed(monkeypatch: pytest.MonkeyPatch):
    plant(monkeypatch, FakeSdkProvider())
    sink = Sink()
    otel.attach(BrokenSink())
    otel.attach(sink)
    otel.PROCESSOR.on_end("span")
    assert sink.spans == ["span"]


def test_processor_meets_the_sdk_span_processor_contract():
    processor = otel.SharpitSpanProcessor()
    processor.on_start("span", None)
    processor._on_ending("span")  # pyright: ignore[reportPrivateUsage] - newer SDKs call it on every processor
    processor.shutdown()
    assert processor.force_flush(1000) is True
