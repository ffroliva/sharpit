"""OpenTelemetry span buffer behind the ``traces`` panel (port of BootUI ``TracesService``, contract §7).

``add`` is the span processor's hot path: one bounded deque append of the SDK's immutable ``ReadableSpan``. Everything
else (grouping, self-trace hiding, masking) happens at read, under the live masker, so the stored evidence is never
changed. Spans are read duck-typed; nothing here imports OpenTelemetry (``engine/otel.py`` is the gatekeeper).
Timestamps are epoch nanoseconds, as the contract says.
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit

from sharpit.engine import otel
from sharpit.engine.capture import under
from sharpit.engine.capture.correlation import INTERNAL
from sharpit.engine.capture.sqltrace import _driver_values_dropped, normalize, normalize_sql  # pyright: ignore[reportPrivateUsage]
from sharpit.engine.capture.streams import SSE_TASK
from sharpit.engine.masking import MASK, Masker, is_sensitive_key

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

MIN_LIMIT, MAX_LIMIT = 1, 500  # TracesService clamp
MAX_SUMMARY_SERVICES = 20
NOT_ARMED = "The tracer provider was set after sharpit started; restart the application to collect traces"
NEVER_ATTACHED = "Trace collection was not attached; the application has not started or capture middleware is absent"
DETACHED = "Trace collection was detached when the application shut down"
_PATH_KEYS = ("http.route", "url.path", "http.target", "url.full", "http.url")
_URL_KEYS = frozenset({"url.full", "http.url"})
_PLAIN_PATH_KEYS = frozenset({"http.route", "url.path", "http.target"})
_SQL_KEYS = frozenset({"db.statement", "db.query.text"})
_HEADER_PREFIXES = ("http.request.header.", "http.response.header.")
_SQL_ERROR = re.compile(r"\[SQL: (.*?)\]", re.DOTALL)
_SQL_PARAMETER_KEYS = re.compile(r"(?:^|[._])(?:parameters?|bind_?params?)(?:[._]|$)", re.IGNORECASE)


def _reveals(masker: Masker) -> bool:
    """True under FULL exposure or with secret masking off: the same switch ``Masker.mask_path`` honours."""
    shown, masked = masker.mask("password", "x")
    return shown is not None and not masked


def _mask_matrix(masker: Masker, path: str) -> str:
    """Mask every ``;name=value`` matrix parameter (BootUI masks them whole: session ids live there)."""
    if ";" not in path or _reveals(masker):
        return path
    segments: list[str] = []
    for segment in path.split("/"):
        head, *params = segment.split(";")
        shown = [f"{p.partition('=')[0]}={MASK}" if "=" in p else MASK for p in params]
        segments.append(";".join([head, *shown]))
    return "/".join(segments)


def _path(masker: Masker, key: str, value: str) -> str:
    """A path attribute as shown: never an absolute URL's scheme or authority, never the query (summary)."""
    path = urlsplit(value).path if key in _URL_KEYS else value.partition("?")[0]
    return _mask_matrix(masker, masker.mask_path(path))


def _url(masker: Masker, key: str, value: str) -> str:
    query = urlsplit(value).query if key in _URL_KEYS else value.partition("?")[2]
    shown = _path(masker, key, value)
    masked_query = masker.mask_query(query) if query else None
    return f"{shown}?{masked_query}" if masked_query else shown


def _kind_name(value: object) -> str:
    match value:
        case bool():
            return "BOOLEAN"
        case int():
            return "LONG"
        case float():
            return "DOUBLE"
        case _:
            return "STRING"


def _items(value: object) -> list[object] | None:
    """An OTel array attribute's items (the SDK stores tuples), else ``None``."""
    return list(cast("Iterable[object]", value)) if isinstance(value, (list, tuple)) else None


def _attribute_type(value: object) -> str:
    items = _items(value)
    if items is not None:
        return f"{_kind_name(items[0]) if items else 'STRING'}_ARRAY"
    return _kind_name(value)


def _text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    items = _items(value)
    if items is not None:
        return "[" + ", ".join(_text(v) for v in items) + "]"
    return str(value)


def _attribute_value(masker: Masker, key: str, value: object) -> str | None:
    if key.startswith(_HEADER_PREFIXES):
        normalized_key = key.lower().replace("-", "_")
        header_name = normalized_key.rsplit(".", 1)[-1].replace("_", "-")
        values = [str(v) for v in _items(value) or [value]]
        if is_sensitive_key(normalized_key) or header_name in {
            "authorization",
            "proxy-authorization",
            "cookie",
            "set-cookie",
            "x-api-key",
        }:
            shown = [MASK for _ in values]
        else:
            shown, _ = masker.mask_header(header_name, values)
        return _text([masker.mask_text(v) or "" for v in shown]) if shown else None
    if _SQL_PARAMETER_KEYS.search(key):
        return _text(value) if masker.capture_parameters else MASK
    if key in _SQL_KEYS:  # SQL Trace normalizes literals unless parameter capture is explicitly enabled
        text = _text(value)
        return masker.mask_text(text if masker.capture_parameters else normalize_sql(text))
    if key in {"exception.message", "exception.stacktrace"}:
        return _sql_message(masker, _text(value))
    if key in _URL_KEYS or key in _PLAIN_PATH_KEYS:
        return _url(masker, key, str(value)) if masker.mask(key, "")[0] is not None else None
    if key == "url.query":
        return masker.mask_query(str(value))
    shown, masked = masker.mask(key, value)
    if shown is None or masked:
        return None if shown is None else str(shown)
    return masker.mask_text(_text(shown))


def _sql_message(masker: Masker, text: str | None) -> str | None:
    if text is None:
        return None
    if not masker.capture_parameters:
        text = _driver_values_dropped(text)
        text = _SQL_ERROR.sub(lambda match: f"[SQL: {normalize(match.group(1)).sql}]", text)
    return masker.mask_text(text)


def _attributes(masker: Masker, attributes: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    return [
        {"key": key, "type": _attribute_type(value), "value": _attribute_value(masker, key, value)}
        for key, value in (attributes or {}).items()
    ]


def _hex(value: int, width: int) -> str:
    return format(value, f"0{width}x")


def _trace_id(span: Any) -> str:
    return _hex(span.context.trace_id, 32)


def _parent_id(span: Any) -> int | None:
    parent = getattr(span, "parent", None)
    return None if parent is None else parent.span_id


def _service(span: Any) -> str | None:
    resource = getattr(span, "resource", None)
    attributes: Mapping[str, Any] = getattr(resource, "attributes", None) or {}
    name = attributes.get("service.name")
    return None if name is None else str(name)


def _kind(span: Any) -> str:
    return str(getattr(span.kind, "name", span.kind))


def _status_code(span: Any) -> str:
    return str(getattr(span.status.status_code, "name", span.status.status_code))


def _raw_path(span: Any) -> tuple[str, str] | None:
    attributes: Mapping[str, Any] = span.attributes or {}
    for key in _PATH_KEYS:
        value = attributes.get(key)
        if isinstance(value, str) and value:
            return key, value
    return None


def _has_ai(span: Any) -> bool:
    attributes: Mapping[str, Any] = span.attributes or {}
    return any(key.startswith("gen_ai.") for key in attributes)


def _plain_path(key: str, value: str) -> str:
    return urlsplit(value).path if key in _URL_KEYS else value.partition("?")[0]


def _without_root_path(path: str, root_path: str) -> str:
    if root_path and (path == root_path or path.startswith(root_path + "/")):
        return path[len(root_path) :] or "/"
    return path


def _request_root_path(root_path: str, self_path: str) -> str:
    return root_path[: -len(self_path)] if self_path and root_path.endswith(self_path) else root_path


def _self_relative_path(path: str, root_path: str, self_path: str) -> str:
    path = _without_root_path(path, _request_root_path(root_path, self_path))
    if not under(path, self_path):
        marker = self_path + "/"
        index = path.find(marker)
        if index > 0 and path[index - 1] == "/":
            path = path[index:]
    return path


class SpanBuffer:
    def __init__(
        self, masker: Masker, *, capacity: int = 1000, self_path: str = "/sharpit", root_path: str = ""
    ) -> None:
        self.masker = masker
        self.root_path = root_path
        self.capacity = capacity
        self.self_path = self_path
        self.armed = False
        self.arm_attempted = False
        self.detached = False
        self._self_trace_ids: set[int] = set()
        self._spans: deque[Any] = deque(maxlen=capacity)  # bounded by spans: memory is what a span buffer costs

    def on_start(self, span: Any) -> None:
        found = _raw_path(span) if getattr(getattr(span, "kind", None), "name", None) == "SERVER" else None
        if found is not None and under(
            _self_relative_path(_plain_path(*found), self.root_path, self.self_path), self.self_path
        ):
            context = getattr(span, "context", None)
            if context is not None:
                self._self_trace_ids.add(context.trace_id)

    def add(self, span: Any) -> None:
        if INTERNAL.get() or SSE_TASK.get():
            return
        context = getattr(span, "context", None)
        if context is None:
            self._spans.append(span)
            return
        trace_id = context.trace_id
        if trace_id in self._self_trace_ids:
            if getattr(getattr(span, "kind", None), "name", None) == "SERVER":
                self._self_trace_ids.discard(trace_id)
            return
        found = _raw_path(span) if getattr(getattr(span, "kind", None), "name", None) == "SERVER" else None
        if found is not None and under(
            _self_relative_path(_plain_path(*found), self.root_path, self.self_path), self.self_path
        ):
            return
        self._spans.append(span)

    def arm(self) -> Callable[[], None] | None:
        """A ``CaptureState.attachers`` entry: arm on the SDK provider, or ``None`` to be retried later."""
        self.arm_attempted = True
        remover = otel.attach(self)
        if remover is None:
            return None
        self.armed = True
        self.detached = False

        def disarm() -> None:
            self.armed = False
            self.detached = True
            remover()

        return disarm

    def clear(self) -> None:
        self._spans.clear()

    def _traces(self) -> dict[str, list[Any]]:
        traces: dict[str, list[Any]] = {}
        for span in self._spans.copy():  # deque.copy is atomic: on_end may append concurrently
            traces.setdefault(_trace_id(span), []).append(span)
        return {tid: spans for tid, spans in traces.items() if not self._is_self(spans)}

    def _is_self(self, spans: Iterable[Any]) -> bool:
        for span in spans:
            found = _raw_path(span) if _kind(span) == "SERVER" else None
            if found is not None and under(
                _self_relative_path(_plain_path(*found), self.root_path, self.self_path), self.self_path
            ):
                return True
        return False

    def _http_path(self, root: Any, spans: list[Any]) -> str | None:
        servers = [s for s in spans if _kind(s) == "SERVER"]
        for span in [root, *servers] if _kind(root) == "SERVER" else servers:
            found = _raw_path(span)
            if found is not None:
                return _path(self.masker, *found)
        return None

    def _summary(self, trace_id: str, spans: list[Any]) -> dict[str, Any]:
        ids = {s.context.span_id for s in spans}
        roots = [s for s in spans if _parent_id(s) not in ids] or spans
        root = min(roots, key=lambda s: s.start_time)
        start = min(s.start_time for s in spans)
        end = max(s.end_time or s.start_time for s in spans)
        services = sorted({name for s in spans if (name := _service(s)) is not None})[:MAX_SUMMARY_SERVICES]
        return {
            "traceId": trace_id,
            "rootSpanName": self.masker.mask_text(root.name),
            "httpPath": self._http_path(root, spans),
            "services": services,
            "startEpochNanos": start,
            "endEpochNanos": end,
            "durationNanos": end - start,
            "spanCount": len(spans),
            "hasError": any(_status_code(s) == "ERROR" for s in spans),
            "hasAi": any(_has_ai(s) for s in spans),
        }

    def unavailable_reason(self) -> str | None:
        if self.armed:
            return None
        if self.detached:
            return DETACHED
        if otel.unavailable_reason() is None:
            return NOT_ARMED if self.arm_attempted else NEVER_ATTACHED
        return otel.unavailable_reason() or NOT_ARMED

    def list(self, limit: int) -> dict[str, Any]:
        limit = min(max(limit, MIN_LIMIT), MAX_LIMIT)
        traces = self._traces()
        rows = sorted(
            (self._summary(tid, spans) for tid, spans in traces.items()),
            key=lambda row: row["startEpochNanos"],
            reverse=True,
        )
        reason = self.unavailable_reason()
        return {
            "enabled": reason is None,
            "unavailableReason": reason,
            "retained": len(traces),
            "capacity": self.capacity,
            "traces": rows[:limit],
        }

    def _span(self, span: Any) -> dict[str, Any]:
        parent = _parent_id(span)
        end = span.end_time or span.start_time
        scope = getattr(span, "instrumentation_scope", None)
        return {
            "traceId": _trace_id(span),
            "spanId": _hex(span.context.span_id, 16),
            "parentSpanId": None if parent is None else _hex(parent, 16),
            "name": self.masker.mask_text(span.name),
            "kind": _kind(span),
            "serviceName": _service(span),
            "scope": getattr(scope, "name", None),
            "startEpochNanos": span.start_time,
            "endEpochNanos": end,
            "durationNanos": end - span.start_time,
            "statusCode": _status_code(span),
            "statusMessage": _sql_message(self.masker, span.status.description),
            "attributes": _attributes(self.masker, span.attributes),
            "events": [
                {
                    "name": self.masker.mask_text(e.name),
                    "timeOffsetNanos": e.timestamp - span.start_time,
                    "attributes": _attributes(self.masker, e.attributes),
                }
                for e in span.events or ()
            ],
        }

    def detail(self, trace_id: str) -> dict[str, Any] | None:
        spans = self._traces().get(trace_id.lower())
        if spans is None:
            return None
        return {
            "traceId": trace_id.lower(),
            "spans": [self._span(s) for s in sorted(spans, key=lambda s: s.start_time)],
        }


def span_buffer(ctx: SharpitContext) -> SpanBuffer:
    """The context's buffer, made on first use (route build); the routes and the MCP tools share it."""
    return ctx.lazy("traces.buffer", lambda: SpanBuffer(ctx.masker, self_path=ctx.settings.path))
