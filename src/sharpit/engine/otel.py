"""OpenTelemetry gatekeeper (AGENTS.md architecture rule 4, spec §6.3): the only module that touches OpenTelemetry.

It never imports ``opentelemetry`` and never installs a ``TracerProvider``: it reads the modules the application already
imported from ``sys.modules`` (as ``sqla.sqlalchemy_module`` does) and adds one module-level span processor to the
application's SDK provider. The SDK cannot remove a processor, so ``attach`` adds it at most once per provider and
detaching only disarms a sink; the next ``attach`` re-arms it.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from typing import Any, Protocol

NO_SDK = "OpenTelemetry SDK is not imported by this application"
NOT_SDK_PROVIDER = "The global tracer provider is not an SDK TracerProvider"
_MISSING = object()


class SpanSink(Protocol):
    def add(self, span: Any) -> None: ...


def otel_sdk() -> Any | None:
    """The imported ``opentelemetry.sdk.trace`` module, else ``None``; never imports it."""
    return sys.modules.get("opentelemetry.sdk.trace")


def _sdk_provider() -> Any | None:
    trace = sys.modules.get("opentelemetry.trace")
    if otel_sdk() is None or trace is None:
        return None
    # The getter may load OTEL_PYTHON_TRACER_PROVIDER's entry point and install it.
    # Reads observe only a provider the application has already configured.
    provider = getattr(trace, "_TRACER_PROVIDER", _MISSING)
    if provider is _MISSING and getattr(trace, "__spec__", None) is None:
        # SDK-shaped test modules from older tests model the provider in a closure;
        # inspect that already-held value without invoking their resolver.
        getter = getattr(trace, "get_tracer_provider", None)
        for cell in getattr(getter, "__closure__", ()) or ():
            try:
                candidate = cell.cell_contents
            except ValueError:
                continue
            if callable(getattr(candidate, "add_span_processor", None)):
                return candidate
    return provider if callable(getattr(provider, "add_span_processor", None)) else None


def unavailable_reason() -> str | None:
    if otel_sdk() is None:
        return NO_SDK
    if _sdk_provider() is None:
        return NOT_SDK_PROVIDER
    return None


class SharpitSpanProcessor:
    """Duck-typed SDK ``SpanProcessor``; ``on_end`` is the hot path: one tuple read and a deque append per sink."""

    def __init__(self) -> None:
        self.sinks: tuple[SpanSink, ...] = ()  # replaced whole under _lock, read lock-free by on_end
        self.providers: list[Any] = []  # every provider this processor was added to (identity, never removed)
        self._lock = threading.Lock()

    def on_start(self, span: Any, parent_context: Any = None) -> None:  # NOSONAR - OpenTelemetry SpanProcessor contract
        for sink in self.sinks:
            try:
                on_start = getattr(sink, "on_start", None)
                if callable(on_start):
                    on_start(span)
            except Exception:  # noqa: BLE001, S112 - never break the host's span pipeline
                continue

    def _on_ending(self, span: Any) -> None:  # newer SDKs call it on every processor
        # This hook needs no action; completed spans are captured by on_end.
        pass

    def on_end(self, span: Any) -> None:
        for sink in self.sinks:
            try:
                sink.add(span)
            except Exception:  # noqa: BLE001, S112 - never break the host's span pipeline
                continue

    def shutdown(self) -> None:
        # nothing to release: spans go to sharpit's in-memory buffer, which install()/uninstall own
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # NOSONAR - OpenTelemetry SpanProcessor contract
        return True


PROCESSOR = SharpitSpanProcessor()


def attach(sink: SpanSink) -> Callable[[], None] | None:
    """Arm ``sink`` on the application's SDK provider; returns its remover, or ``None`` when no SDK provider is set."""
    provider = _sdk_provider()
    if provider is None:
        return None
    processor = PROCESSOR
    with processor._lock:  # pyright: ignore[reportPrivateUsage]
        if not any(p is provider for p in processor.providers):
            provider.add_span_processor(processor)
            processor.providers.append(provider)
        if not any(s is sink for s in processor.sinks):
            processor.sinks = (*processor.sinks, sink)
    return lambda: disarm(sink, processor)


def disarm(sink: SpanSink, processor: SharpitSpanProcessor | None = None) -> None:
    processor = processor or PROCESSOR
    with processor._lock:  # pyright: ignore[reportPrivateUsage]
        processor.sinks = tuple(s for s in processor.sinks if s is not sink)
