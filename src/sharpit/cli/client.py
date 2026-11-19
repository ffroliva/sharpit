"""HTTP client for a running sharpit application."""

from __future__ import annotations

import http.client as _http_client
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, cast
from urllib import request as _request
from urllib.parse import quote, urlsplit

from sharpit import __version__

# Default response cap for ordinary calls; bounded calls accept the caller's limit.
_MAX_RESPONSE_BYTES = 1_048_576
_PANEL_ACCESS_DENIED = "sharpit panel access denied"
__all__ = ["Client", "ClientError", "ToolResult"]


class _NoRedirect(_request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        return None


class ClientError(Exception):
    """A safe-to-display CLI transport failure."""


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_name: str
    status: int
    raw_body: str
    payload: Any


class Client:
    def __init__(self, options: Any) -> None:
        self.options = options
        self.options.timeout = _valid_timeout(options.timeout)
        token = options.token
        if token and any(ord(char) < 32 or 127 <= ord(char) <= 159 or ord(char) > 255 for char in token):
            raise ClientError("The token contains characters an HTTP header cannot carry")
        self._opener = _request.build_opener(_request.ProxyHandler({}), _NoRedirect())

    def get(self, path: str) -> Any:
        return self._get(path, _MAX_RESPONSE_BYTES, None)

    def get_bounded(self, path: str, max_response_bytes: int, timeout: float | None = None) -> Any:
        return self._get(path, max_response_bytes, self.options.timeout if timeout is None else timeout)

    def invoke(self, tool: str, arguments: dict[str, Any]) -> ToolResult:
        return self._invoke(tool, arguments, _MAX_RESPONSE_BYTES, None)

    def invoke_bounded(
        self, tool: str, arguments: dict[str, Any], max_response_bytes: int, timeout: float | None = None
    ) -> ToolResult:
        return self._invoke(tool, arguments, max_response_bytes, self.options.timeout if timeout is None else timeout)

    def catalog(self) -> dict[str, Any]:
        return self._catalog(_MAX_RESPONSE_BYTES, None)

    def catalog_bounded(self, max_response_bytes: int, timeout: float | None = None) -> Any:
        return self._catalog(max_response_bytes, self.options.timeout if timeout is None else timeout)

    def _get(self, path: str, max_response_bytes: int, timeout: float | None) -> Any:
        endpoint = self._endpoint(path)
        status, body = self._send(endpoint, "GET", None, max_response_bytes, timeout)
        if not 200 <= status < 300:
            raise self._describe_failure(status, body)
        return _parse_json(body, endpoint, status)

    def _invoke(
        self,
        tool: str,
        arguments: dict[str, Any],
        max_response_bytes: int,
        timeout: float | None,
    ) -> ToolResult:
        path = f"/cli/tools/{quote(tool, safe='')}"
        endpoint = self._endpoint(path)
        status, body = self._send(endpoint, "POST", arguments, max_response_bytes, timeout)
        if not 200 <= status < 300:
            return ToolResult(tool, status, body, _optional_json(body))
        payload = _parse_json(body, endpoint, status)
        return ToolResult(tool, status, body, payload)

    def _catalog(self, max_response_bytes: int, timeout: float | None) -> dict[str, Any]:
        path = "/cli"
        endpoint = self._endpoint(path)
        status, body = self._send(endpoint, "GET", None, max_response_bytes, timeout)
        if status == 404:
            raise self._client_error(
                f"No sharpit command-line endpoint at {endpoint}. The application may predate it, "
                "be running sharpit at a different --api-path, or not be a sharpit application."
            )
        if not 200 <= status < 300:
            raise self._describe_failure(status, body)
        payload = _parse_json(body, endpoint, status)
        if (
            not isinstance(payload, dict)
            or payload.get("serverName") != "sharpit"
            or not isinstance(payload.get("enabled"), bool)
            or not isinstance(payload.get("tools"), list)
            or (not payload["enabled"] and payload["tools"])
        ):
            raise self._client_error(
                "Response is not a sharpit catalog: expected serverName 'sharpit', a boolean enabled, "
                "and a tools array that is empty while disabled."
            )
        return payload

    def _send(
        self,
        endpoint: str,
        method: str,
        arguments: dict[str, Any] | None,
        max_response_bytes: int,
        timeout: float | None,
    ) -> tuple[int, str]:
        self._validate_url(endpoint)
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")

        base = self.options.base_url.rstrip("/")
        configured_timeout = _valid_timeout(self.options.timeout)
        request_timeout = configured_timeout if timeout is None else min(configured_timeout, float(timeout))
        if request_timeout <= 0:
            raise self._client_error(f"Request to {base} exceeded its response deadline.")
        deadline = time.monotonic() + request_timeout
        try:
            outgoing = self._request(endpoint, method, arguments)
        except ValueError:
            raise self._client_error("Request could not be encoded for HTTP") from None
        outcome = self._exchange(
            outgoing, deadline, request_timeout, max_response_bytes, base, configured_timeout, timeout
        )
        status, body = outcome
        if not 200 <= status < 300:
            return status, body.decode("utf-8", errors="replace")
        return status, self._decode_body(body)

    def _exchange(
        self,
        outgoing: Any,
        deadline: float,
        request_timeout: float,
        max_response_bytes: int,
        base: str,
        configured_timeout: float,
        timeout: float | None,
    ) -> tuple[int, bytes]:
        result: list[tuple[int, bytes] | Exception] = []

        def perform() -> None:
            try:
                with self._open_response(outgoing, min(request_timeout, 10.0)) as response:
                    status = cast(int, getattr(response, "status", getattr(response, "code", 0)))
                    result.append((status, _read_bounded(response, deadline, max_response_bytes)))
            except Exception as error:
                result.append(error)

        worker = threading.Thread(target=perform, daemon=True)
        worker.start()
        worker.join(max(0.0, deadline - time.monotonic()))
        if worker.is_alive():
            raise self._timeout_error(base, configured_timeout, timeout is not None)
        outcome = result[0]
        if isinstance(outcome, Exception):
            raise self._request_error(outcome, base, configured_timeout, timeout) from None
        return outcome

    def _request_error(self, error: Exception, base: str, timeout: float, request_timeout: float | None) -> ClientError:
        if isinstance(error, ClientError):
            return error
        if isinstance(error, TimeoutError):
            return self._timeout_error(base, timeout, request_timeout is not None)
        if isinstance(error, (_http_client.HTTPException, OSError)):
            return self._transport_error(error, base)
        if isinstance(error, (ValueError, UnicodeEncodeError)):
            return self._client_error("Request could not be encoded for HTTP")
        return self._client_error("Request failed")

    def _validate_url(self, endpoint: str) -> None:
        try:
            parsed = urlsplit(endpoint)
        except ValueError:
            raise self._client_error(f"Not a valid URL: {endpoint}") from None
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise self._client_error(f"Not a valid URL: {endpoint}")

    def _request(self, endpoint: str, method: str, arguments: dict[str, Any] | None) -> Any:
        headers = {"Accept": "application/json", "User-Agent": f"sharpit/{__version__}"}
        data = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            data = json.dumps(arguments or {}).encode("utf-8")
        if self.options.token:
            headers["Authorization"] = f"Bearer {self.options.token}"
        return _request.Request(endpoint, data=data, headers=headers, method=method)  # noqa: S310

    def _open_response(self, outgoing: Any, timeout: float) -> Any:
        try:
            return self._opener.open(outgoing, timeout=timeout)
        except _request.HTTPError as error:
            if error.code in (301, 302, 303, 307, 308):
                error.close()
                raise self._client_error(f"Request was redirected (HTTP {error.code})") from None
            return error
        except OSError:
            raise self._client_error(
                f"Cannot reach sharpit at {self.options.base_url.rstrip('/')}. "
                "Is the application running, and is that the right --url?"
            ) from None

    def _transport_error(self, error: Exception, base: str) -> ClientError:
        if isinstance(error, OSError):
            return self._client_error(
                f"Cannot reach sharpit at {base}. Is the application running, and is that the right --url?"
            )
        return self._client_error(f"Request to {base} failed: {error}")

    def _decode_body(self, body: bytes) -> str:
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            raise self._client_error("Response is not valid UTF-8") from None

    def _timeout_error(self, base: str, timeout: float, bounded: bool) -> ClientError:
        if bounded:
            return self._client_error(f"Request to {base} exceeded its response deadline.")
        return self._client_error(
            f"No response from {base} within {int(timeout)}s. Raise --timeout if the tool is expected to be slow."
        )

    def _describe_failure(self, status: int, body: str) -> ClientError:
        error = reason = message = panel = None
        try:
            parsed = _strict_json(body)
            if isinstance(parsed, dict):
                document = cast("dict[str, Any]", parsed)
                error = _nonblank(document.get("error"))
                reason = _nonblank(document.get("reason"))
                message = _nonblank(document.get("message"))
                panel = _nonblank(document.get("panel"))
        except (ValueError, ClientError):
            pass

        specific = reason or message
        detail = f": {error}" if error else ""
        if specific and specific != error:
            detail += f": {specific}"
        panel_refusal = status == 403 and panel is not None and reason is not None and error == _PANEL_ACCESS_DENIED
        if status == 401 or (status == 403 and not panel_refusal):
            text = (
                f"sharpit refused the request (HTTP {status}){detail}. A non-loopback --url needs --token, "
                "and sharpit only answers requests it considers local."
            )
        else:
            text = f"sharpit answered HTTP {status}{detail}"
        return self._client_error(text)

    def _endpoint(self, path: str) -> str:
        base = self.options.base_url.rstrip("/")
        api = self.options.api_path.rstrip("/")
        return f"{base}{api}{path if path.startswith('/') else '/' + path}"

    def _client_error(self, message: str) -> ClientError:
        token = self.options.token
        if token:
            message = _redact(message, token)
        message = _sharpit_text(message)
        return ClientError(message)


def _read_bounded(response: Any, deadline: float, max_response_bytes: int = _MAX_RESPONSE_BYTES) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("response deadline exceeded")
        raw = getattr(getattr(response, "fp", None), "raw", None)
        sock = getattr(raw, "_sock", None)
        settimeout = getattr(sock, "settimeout", None)
        if callable(settimeout):
            settimeout(remaining)
        chunk = response.read1(min(65536, max_response_bytes + 1 - total))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_response_bytes:
            raise ClientError(f"Response exceeded the {max_response_bytes} byte limit")
        chunks.append(chunk)


def _parse_json(body: str, endpoint: str, status: int) -> Any:
    try:
        return _strict_json(body)
    except ValueError:
        raise ClientError(f"Response from {endpoint} does not contain JSON (HTTP {status})") from None


def _strict_json(body: str) -> Any:
    try:
        return json.loads(body, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except RecursionError:
        raise ClientError("Response was not valid strict JSON") from None


def _optional_json(body: str) -> Any:
    try:
        return _strict_json(body)
    except (ValueError, ClientError):
        return None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError(f"invalid JSON constant: {value}")


def _nonblank(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def nonblank(value: Any) -> str | None:
    return _nonblank(value)


def _sharpit_text(text: str) -> str:
    return text.replace("BootUI", "sharpit").replace("bootui.", "sharpit.")


def _redact(text: str, token: str | None) -> str:
    if token:
        text = text.replace(f"Authorization: Bearer {token}", "[redacted]")
        text = text.replace(f"Bearer {token}", "Bearer [redacted]").replace(token, "[redacted]")
    return text


def redact(text: str, token: str | None) -> str:
    return _redact(text, token)


def sharpit_text(text: str) -> str:
    return _sharpit_text(text)


def _valid_timeout(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return 60.0
    return timeout if 0 < timeout < float("inf") else 60.0
