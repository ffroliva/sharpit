"""HTTP client for a running sharpit application."""

from __future__ import annotations

import http.client as http_client
import json
import time
from dataclasses import dataclass
from typing import Any, cast
from urllib import request
from urllib.parse import urlsplit

from sharpit import __version__

# Default response cap for ordinary calls; bounded calls accept the caller's limit.
_MAX_RESPONSE_BYTES = 1_048_576


class _NoRedirect(request.HTTPRedirectHandler):
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
        self._opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())

    def get(self, path: str) -> Any:
        return self._get(path, _MAX_RESPONSE_BYTES, None, False)

    def get_bounded(self, path: str, max_response_bytes: int, timeout: float | None = None) -> Any:
        return self._get(path, max_response_bytes, timeout, True)

    def invoke(self, tool: str, arguments: dict[str, Any]) -> ToolResult:
        return self._invoke(tool, arguments, _MAX_RESPONSE_BYTES, None, False)

    def invoke_bounded(
        self, tool: str, arguments: dict[str, Any], max_response_bytes: int, timeout: float | None = None
    ) -> ToolResult:
        return self._invoke(tool, arguments, max_response_bytes, timeout, True)

    def catalog(self) -> Any:
        return self._catalog(_MAX_RESPONSE_BYTES, None, False)

    def catalog_bounded(self, max_response_bytes: int, timeout: float | None = None) -> Any:
        return self._catalog(max_response_bytes, timeout, True)

    def _get(self, path: str, max_response_bytes: int, timeout: float | None, bounded: bool) -> Any:
        endpoint = self._endpoint(path)
        status, body = self._send(path, "GET", None, max_response_bytes, timeout, bounded)
        if not 200 <= status < 300:
            raise self._describe_failure(status, body)
        return _parse_json(body, endpoint, status, self.options.token)

    def _invoke(
        self,
        tool: str,
        arguments: dict[str, Any],
        max_response_bytes: int,
        timeout: float | None,
        bounded: bool,
    ) -> ToolResult:
        path = f"/cli/tools/{tool}"
        endpoint = self._endpoint(path)
        status, body = self._send(path, "POST", arguments, max_response_bytes, timeout, bounded)
        payload = _parse_json(body, endpoint, status, self.options.token)
        return ToolResult(tool, status, body, payload)

    def _catalog(self, max_response_bytes: int, timeout: float | None, bounded: bool) -> Any:
        path = "/cli"
        endpoint = self._endpoint(path)
        status, body = self._send(path, "GET", None, max_response_bytes, timeout, bounded)
        if status == 404:
            raise self._client_error(
                f"No sharpit command-line endpoint at {endpoint}. The application may predate it, "
                "be running sharpit at a different --api-path, or not be a sharpit application."
            )
        if not 200 <= status < 300:
            raise self._describe_failure(status, body)
        return _parse_json(body, endpoint, status, self.options.token)

    def _send(
        self,
        path: str,
        method: str,
        arguments: dict[str, Any] | None,
        max_response_bytes: int,
        timeout: float | None,
        bounded: bool,
    ) -> tuple[int, str]:
        endpoint = self._endpoint(path)
        self._validate_url(endpoint)
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")

        base = self.options.base_url.rstrip("/")
        configured_timeout = float(self.options.timeout)
        request_timeout = configured_timeout if timeout is None else min(configured_timeout, float(timeout))
        if request_timeout <= 0:
            raise self._client_error(f"Request to {base} exceeded its response deadline.")
        deadline = time.monotonic() + request_timeout
        outgoing = self._request(endpoint, method, arguments)
        try:
            with self._open_response(outgoing, request_timeout) as response:
                status = getattr(response, "status", getattr(response, "code", 0))
                body = _read_bounded(response, deadline, max_response_bytes)
        except ClientError:
            raise
        except request.URLError as error:  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
            raise self._transport_error(cast(Exception, error), base, configured_timeout, bounded) from None
        except (http_client.HTTPException, TimeoutError, OSError) as error:
            raise self._transport_error(error, base, configured_timeout, bounded) from None

        return status, self._decode_body(body)

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
        return request.Request(endpoint, data=data, headers=headers, method=method)  # noqa: S310

    def _open_response(self, outgoing: Any, timeout: float) -> Any:
        try:
            return self._opener.open(outgoing, timeout=timeout)
        except request.HTTPError as error:
            if error.code in (301, 302, 303, 307, 308):
                raise self._client_error(f"Request was redirected (HTTP {error.code})") from None
            return error

    def _transport_error(self, error: Exception, base: str, timeout: float, bounded: bool) -> ClientError:
        reason = getattr(error, "reason", error)
        if isinstance(reason, TimeoutError):
            return self._timeout_error(base, timeout, bounded)
        if isinstance(reason, ConnectionError):
            return self._client_error(
                f"Cannot reach sharpit at {base}. Is the application running, and is that the right --url?"
            )
        return self._client_error(f"Request to {base} failed: {reason}")

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
            parsed: Any = json.loads(body, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
            if isinstance(parsed, dict):
                document = cast("dict[str, Any]", parsed)
                error = _nonblank(document.get("error"))
                reason = _nonblank(document.get("reason"))
                message = _nonblank(document.get("message"))
                panel = _nonblank(document.get("panel"))
        except (json.JSONDecodeError, ValueError):
            pass

        specific = reason or message
        detail = f": {error}" if error else ""
        if specific and specific != error:
            detail += f": {specific}"
        panel_refusal = (
            status == 403 and panel is not None and reason is not None and error == "BootUI panel access denied"
        )
        if status == 401 or (status == 403 and not panel_refusal):
            text = (
                f"sharpit refused the request (HTTP {status}){detail}. A non-loopback --url needs --token, "
                "and sharpit only answers requests it considers local."
            )
        else:
            text = f"sharpit answered HTTP {status}{detail}"
        return self._client_error(_sharpit_text(text))

    def _endpoint(self, path: str) -> str:
        base = self.options.base_url.rstrip("/")
        api = self.options.api_path.rstrip("/")
        return f"{base}{api}{path if path.startswith('/') else '/' + path}"

    def _client_error(self, message: str) -> ClientError:
        token = self.options.token
        if token:
            message = message.replace(f"Authorization: Bearer {token}", "[redacted]")
            message = message.replace(f"Bearer {token}", "Bearer [redacted]").replace(token, "[redacted]")
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


def _parse_json(body: str, endpoint: str, status: int, token: str | None) -> Any:
    try:
        return json.loads(body, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError):
        message = f"Response from {endpoint} does not contain JSON (HTTP {status})"
        if token:
            message = message.replace(token, "[redacted]")
        raise ClientError(message) from None


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


def _sharpit_text(text: str) -> str:
    return text.replace("BootUI", "sharpit").replace("bootui.", "sharpit.")
