"""Bounded, in-process HTTP probes (spec §7.11)."""

from __future__ import annotations

import asyncio
import posixpath
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import quote, unquote, urlsplit

import anyio
from starlette.types import Message, Scope

from sharpit.engine.capture import under
from sharpit.engine.masking import Masker
from sharpit.engine.paging import BadRequest

MAX_METHOD_BYTES = 32
MAX_PATH_BYTES = 2048
MAX_REQUEST_BODY_BYTES = 64 * 1024
MAX_HEADER_COUNT = 50
MAX_HEADER_NAME_BYTES = 256
MAX_HEADER_VALUE_BYTES = 8 * 1024
MAX_TOTAL_HEADER_BYTES = 32 * 1024
MAX_RESPONSE_BODY_BYTES = 1 << 20
PROBE_TIMEOUT = 10.0
RESTRICTED_HEADERS = frozenset(
    {
        "host",
        "connection",
        "content-length",
        "expect",
        "upgrade",
        "transfer-encoding",
        "proxy-connection",
        "keep-alive",
        "te",
        "x-sharpit-probe",
    }
)
ALLOWED_RESPONSE_HEADERS = frozenset({"content-type", "content-length", "location"})
_HEADER_TOKEN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$", re.ASCII)
_METHODS = "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS"


@dataclass(frozen=True)
class ProbeRequest:
    method: str
    path: str
    body: str
    headers: dict[str, str]


def _utf8_size(value: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise BadRequest("HTTP Probe request contains invalid Unicode") from exc


def _normal_path(path: str) -> str:
    decoded = unquote(path)
    leading = decoded.startswith("/")
    normalized = posixpath.normpath(decoded)
    return ("/" + normalized.lstrip("/")) if leading else normalized


def validate_probe(body: dict[str, Any], settings_path: str, host_root_path: str = "") -> ProbeRequest:
    method = body.get("method")
    if method is None or not str(method).strip():
        method = "GET"
    if not isinstance(method, str):
        raise BadRequest("HTTP Probe request method is invalid")
    if _utf8_size(method) > MAX_METHOD_BYTES:
        raise BadRequest(f"HTTP Probe request method exceeds the maximum of {MAX_METHOD_BYTES} bytes")
    method = method.strip().upper()
    if method not in _METHODS.split(", "):
        raise BadRequest(f"HTTP Probe request method must be one of {_METHODS}")

    path = body.get("path")
    if path is None or not str(path).strip():
        path = "/"
    if not isinstance(path, str):
        raise BadRequest("HTTP Probe request path is invalid")
    if _utf8_size(path) > MAX_PATH_BYTES:
        raise BadRequest(f"HTTP Probe request path exceeds the maximum of {MAX_PATH_BYTES} bytes")
    parsed = urlsplit(path)
    if not path.startswith("/"):
        raise BadRequest("HTTP Probe request path must start with '/'")
    if parsed.scheme or parsed.netloc or path.startswith("//"):
        raise BadRequest("HTTP Probe request path must not include a host")
    decoded_path = unquote(parsed.path)
    segments = decoded_path.split("/")
    if ".." in segments:
        raise BadRequest("HTTP Probe request path must not contain '..' segments")
    normalized = _normal_path(parsed.path)
    host_mount = host_root_path.rstrip("/") + settings_path
    if under(normalized, settings_path) or under(normalized, host_mount):
        raise BadRequest("HTTP Probe cannot target sharpit itself")

    payload = body.get("body")
    if payload is None:
        payload = ""
    if not isinstance(payload, str):
        raise BadRequest("HTTP Probe request body must be a string")
    if _utf8_size(payload) > MAX_REQUEST_BODY_BYTES:
        raise BadRequest(f"HTTP Probe request body exceeds the maximum of {MAX_REQUEST_BODY_BYTES} bytes")

    raw_headers = body.get("headers")
    if raw_headers is None:
        raw_headers = {}
    if not isinstance(raw_headers, dict):
        raise BadRequest("HTTP Probe request headers must be an object")
    raw_headers = cast("dict[object, object]", raw_headers)
    if len(raw_headers) > MAX_HEADER_COUNT:
        raise BadRequest(f"HTTP Probe request exceeds the maximum of {MAX_HEADER_COUNT} request headers")
    headers: dict[str, str] = {}
    total = 0
    for name, value in raw_headers.items():
        if not isinstance(name, str) or _utf8_size(name) > MAX_HEADER_NAME_BYTES:
            raise BadRequest(f"HTTP Probe request header name exceeds the maximum of {MAX_HEADER_NAME_BYTES} bytes")
        if not _HEADER_TOKEN.fullmatch(name):
            raise BadRequest("HTTP Probe request header name is invalid")
        if value is None:
            continue
        if not isinstance(value, str):
            raise BadRequest("HTTP Probe request header value is invalid")
        value_size = _utf8_size(value)
        if value_size > MAX_HEADER_VALUE_BYTES:
            raise BadRequest(f"HTTP Probe request header value exceeds the maximum of {MAX_HEADER_VALUE_BYTES} bytes")
        if any(char in value for char in "\r\n\x00"):
            raise BadRequest("HTTP Probe request header value contains a forbidden character")
        total += _utf8_size(name) + value_size
        if total > MAX_TOTAL_HEADER_BYTES:
            raise BadRequest(f"HTTP Probe request headers exceed the maximum total of {MAX_TOTAL_HEADER_BYTES} bytes")
        lowered = name.lower()
        if lowered not in RESTRICTED_HEADERS:
            headers[lowered] = value
    return ProbeRequest(method, path, payload, headers)


class ProbeSlots:
    """Thread-safe cap shared by probes handled on different event loops."""

    def __init__(self, limit: int = 4) -> None:
        self.limit = limit
        self._count = 0
        self._lock = threading.Lock()

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def acquire(self) -> bool:
        with self._lock:
            if self._count >= self.limit:
                return False
            self._count += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._count = max(0, self._count - 1)


def _status_text(status: int) -> str:
    return {
        200: "OK",
        201: "Created",
        204: "No Content",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        500: "Internal Server Error",
    }.get(status, f"HTTP {status}")


def _headers(headers: list[tuple[bytes, bytes]], masker: Masker) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for key, value in headers:
        name = key.decode("latin-1").lower()
        if name in ALLOWED_RESPONSE_HEADERS:
            grouped.setdefault(name, []).append(value.decode("latin-1"))
    result = {name: ", ".join(values) for name, values in grouped.items()}
    if "location" in result:
        masked = (masker.mask_text(result["location"]) or "").encode("utf-8")[:MAX_HEADER_VALUE_BYTES]
        result["location"] = masked.decode("utf-8", errors="ignore")
    return result


def _body(raw: bytes, content_type: str | None, masker: Masker) -> str | None:
    if not raw:
        return ""
    if content_type is not None:
        media_type = content_type.partition(";")[0].strip().lower()
        textual = media_type.startswith("text/") or any(
            marker in media_type for marker in ("json", "xml", "javascript", "x-www-form-urlencoded")
        )
        if not textual:
            return f"<{len(raw)} bytes, {content_type}>"
    text = raw.decode("utf-8", errors="replace")
    return masker.mask_text(text)


def _task_done(task: asyncio.Task[Any], on_complete: Callable[[], None]) -> None:
    """Retrieve a late exception before releasing the slot so asyncio cannot log unmasked app data."""
    if not task.cancelled():
        task.exception()
    on_complete()


_PENDING_TASKS: set[asyncio.Task[Any]] = set()


async def run_probe(
    host_app: Any,
    request: ProbeRequest,
    caller_scope: Mapping[str, Any],
    host_root_path: str,
    masker: Masker,
    timeout: float = PROBE_TIMEOUT,
    max_body: int = MAX_RESPONSE_BODY_BYTES,
    on_complete: Callable[[], None] | None = None,
) -> dict[str, Any]:
    parsed = urlsplit(request.path)
    path_prefix = host_root_path.rstrip("/")
    raw_path = quote(path_prefix + parsed.path, safe="/%:@!$&'()*+,;=-._~").encode("ascii")
    request_body = request.body.encode("utf-8") if request.method in {"POST", "PUT", "PATCH"} else b""
    incoming = [
        (name.encode("latin-1"), value.encode("latin-1", errors="replace")) for name, value in request.headers.items()
    ]
    for name, value in caller_scope.get("headers", ()):
        if name.lower() == b"host":
            incoming.append((b"host", value))
            break
    incoming.append((b"x-sharpit-probe", b"1"))
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": request.method,
        "scheme": "http",
        "path": path_prefix + unquote(parsed.path),
        "raw_path": raw_path,
        "query_string": quote(parsed.query, safe="%=&;/:@!$'()*+,-._~?").encode("ascii"),
        "root_path": host_root_path,
        "headers": incoming,
        "client": caller_scope.get("client"),
        "server": caller_scope.get("server"),
        "state": dict(caller_scope.get("state", {})),
        "extensions": {"sharpit.probe": True},
    }
    sent_body = bytearray()
    response_headers: list[tuple[bytes, bytes]] = []
    status = 0
    truncated = False
    finished = asyncio.Event()
    first_receive = True

    async def receive() -> Message:
        nonlocal first_receive
        if first_receive:
            first_receive = False
            return {"type": "http.request", "body": request_body, "more_body": False}
        await finished.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        nonlocal status, response_headers, truncated
        if message["type"] == "http.response.start":
            status = message["status"]
            response_headers = list(message.get("headers", []))
        elif message["type"] == "http.response.body":
            chunk = message.get("body", b"")
            room = max(0, max_body - len(sent_body))
            sent_body.extend(chunk[:room])
            if len(chunk) > room:
                truncated = True
                raise asyncio.CancelledError

    started = time.monotonic()
    cancel_scopes: list[anyio.CancelScope] = []

    async def invoke_host() -> None:
        with anyio.CancelScope() as cancel_scope:
            cancel_scopes.append(cancel_scope)
            await host_app(scope, receive, send)

    task = asyncio.create_task(invoke_host())
    transferred_slot = False
    try:
        done, _ = await asyncio.wait({task}, timeout=timeout)
        if not done:
            # AnyIO delays cancellation until a sync endpoint's worker thread has returned.
            finished.set()
            if cancel_scopes:
                cancel_scopes[0].cancel()
            else:
                task.cancel()
            _PENDING_TASKS.add(task)
            if on_complete is not None:

                def finish(completed: asyncio.Task[Any]) -> None:
                    _PENDING_TASKS.discard(completed)
                    _task_done(completed, on_complete)

                task.add_done_callback(finish)
                transferred_slot = True
            else:
                task.add_done_callback(lambda completed: _PENDING_TASKS.discard(completed))
            return {
                "status": status,
                "statusText": _status_text(status) if status else "Error",
                "headers": {},
                "body": _body(bytes(sent_body), None, masker),
                "durationMs": round((time.monotonic() - started) * 1000),
                "error": f"HTTP Probe timed out after {timeout:g}s",
                "truncated": False,
            }
        await task
    except asyncio.CancelledError:
        if not truncated:
            task.cancel()
            if on_complete is not None and not transferred_slot:
                task.add_done_callback(lambda completed: _task_done(completed, on_complete))
                transferred_slot = True
            raise
    except Exception as exc:  # noqa: BLE001 - app exceptions become a stable masked probe response
        message = masker.mask_text(f"{type(exc).__name__}: {exc}") or type(exc).__name__
        status = 500
        return {
            "status": status,
            "statusText": _status_text(status),
            "headers": {},
            "body": _body(bytes(sent_body), None, masker),
            "durationMs": round((time.monotonic() - started) * 1000),
            "error": message,
            "truncated": False,
        }
    finally:
        finished.set()
        if on_complete is not None and not transferred_slot:
            on_complete()
    headers = _headers(response_headers, masker)
    body = _body(bytes(sent_body), headers.get("content-type"), masker)
    return {
        "status": status,
        "statusText": _status_text(status) if status else "Error",
        "headers": headers,
        "body": body,
        "durationMs": round((time.monotonic() - started) * 1000),
        "error": "HTTP Probe target returned no response" if status == 0 else None,
        "truncated": truncated,
    }
