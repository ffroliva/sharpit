"""The OpenTelemetry gatekeeper (lane A-traces, spec §6.3): reads ``sys.modules``, never imports or installs OTel.

The SDK is not a test dependency, so these tests plant SDK-shaped modules in ``sys.modules``; the processor only
relies on the duck-typed ``add_span_processor`` / ``on_end`` contract.
"""

# ruff: noqa: E501  # the frozen red's test helper docstring documents a long OpenTelemetry API name

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


def plant_api(monkeypatch: pytest.MonkeyPatch, provider: Any, calls: list[str]) -> None:
    """The real API's shape: a ``_TRACER_PROVIDER`` global (None until set) and a getter that may load an entry point."""
    trace = ModuleType("opentelemetry.trace")
    trace._TRACER_PROVIDER = provider  # type: ignore[attr-defined]
    trace.get_tracer_provider = lambda: calls.append("get_tracer_provider") or FakeSdkProvider()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", ModuleType("opentelemetry.sdk.trace"))


def test_unset_provider_is_never_resolved_through_the_getter(monkeypatch: pytest.MonkeyPatch):
    # review r1: get_tracer_provider() loads OTEL_PYTHON_TRACER_PROVIDER's entry point and installs it: a GET must not
    calls: list[str] = []
    plant_api(monkeypatch, None, calls)
    otel.unavailable_reason()
    assert calls == []


def test_unset_provider_is_unavailable(monkeypatch: pytest.MonkeyPatch):
    plant_api(monkeypatch, None, [])
    assert otel.unavailable_reason() == otel.NOT_SDK_PROVIDER


def test_set_provider_is_read_from_the_global(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    provider = FakeSdkProvider()
    plant_api(monkeypatch, provider, calls)
    otel.attach(Sink())
    assert calls == []


@pytest.fixture
def real_api_without_global_provider(monkeypatch: pytest.MonkeyPatch) -> Any:
    """The real OpenTelemetry API with no global tracer provider set, as when an app passes its provider directly."""
    trace = pytest.importorskip("opentelemetry.trace")
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace)
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", None)
    return trace


def test_trace_id_of_a_span_from_a_non_global_provider(real_api_without_global_provider: Any):
    # council 0.9.0: instrument_app(app, tracer_provider=tp) never sets the global provider; its spans keep their id
    from opentelemetry.sdk.trace import TracerProvider

    with TracerProvider().get_tracer("t").start_as_current_span("q") as span:
        expected = f"{span.get_span_context().trace_id:032x}"
        assert otel.current_trace_id() == expected


def test_trace_id_of_a_propagated_remote_span_context(real_api_without_global_provider: Any):
    trace = real_api_without_global_provider
    remote = trace.SpanContext(0x0AF7651916CD43DD8448EB211C80319C, 0xB7AD6B7169203331, is_remote=True)
    with trace.use_span(trace.NonRecordingSpan(remote)):
        assert otel.current_trace_id() == "0af7651916cd43dd8448eb211c80319c"


def test_no_trace_id_without_a_current_span(real_api_without_global_provider: Any):
    assert otel.current_trace_id() is None
