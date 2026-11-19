"""HTTP client for a running sharpit application."""

from __future__ import annotations

import http.client as _http_client
import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, cast
from urllib import request as _request
from urllib.parse import quote, urlsplit

from sharpit import __version__
from sharpit.cli.options import ClientOptions

_CONNECT_TIMEOUT = 10.0
_PANEL_ACCESS_DENIED = "sharpit panel access denied"
__all__ = ["Client", "ClientError", "ToolResult", "error_body", "safe_text"]

JsonObject = dict[str, Any]  # a decoded JSON object


class _NoRedirect(_request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        return None


class ClientError(Exception):
    """A safe-to-display CLI transport failure."""

    def __init__(self, message: str, *, status: int | None = None, body: str = "", request_sent: bool = False) -> None:
        self.status = status
        self.body = body
        self.request_sent = request_sent
        super().__init__(message)


class _TimeoutHTTPConnection(_http_client.HTTPConnection):
    def __init__(self, *args: Any, read_timeout: float, on_send: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._read_timeout = read_timeout
        self._on_send = on_send

    def send(self, data: Any) -> None:
        super().send(data)
        self._on_send()

    def getresponse(self) -> _http_client.HTTPResponse:
        if self.sock is not None:
            self.sock.settimeout(self._read_timeout)
        return super().getresponse()


class _TimeoutHTTPSConnection(_http_client.HTTPSConnection):
    def __init__(self, *args: Any, read_timeout: float, on_send: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._read_timeout = read_timeout
        self._on_send = on_send

    def send(self, data: Any) -> None:
        super().send(data)
        self._on_send()

    def getresponse(self) -> _http_client.HTTPResponse:
        if self.sock is not None:
            self.sock.settimeout(self._read_timeout)
        return super().getresponse()


class _TimeoutHTTPHandler(_request.HTTPHandler):
    def __init__(self, read_timeout: float, on_send: Any) -> None:
        super().__init__()
        self.read_timeout = read_timeout
        self.on_send = on_send

    def http_open(self, req: Any) -> Any:
        def connection(host: str, **kwargs: Any) -> _TimeoutHTTPConnection:
            return _TimeoutHTTPConnection(host, read_timeout=self.read_timeout, on_send=self.on_send, **kwargs)

        return self.do_open(cast("Any", connection), req)


class _TimeoutHTTPSHandler(_request.HTTPSHandler):
    def __init__(self, read_timeout: float, on_send: Any) -> None:
        super().__init__()
        self.read_timeout = read_timeout
        self.on_send = on_send

    def https_open(self, req: Any) -> Any:
        def connection(host: str, **kwargs: Any) -> _TimeoutHTTPSConnection:
            return _TimeoutHTTPSConnection(host, read_timeout=self.read_timeout, on_send=self.on_send, **kwargs)

        return self.do_open(cast("Any", connection), req)


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Raw server data; callers must redact it before displaying or logging it."""

    tool_name: str
    status: int
    raw_body: str
    payload: Any


class Client:
    def __init__(self, options: ClientOptions) -> None:
        self.options = options
        self.timeout = _valid_timeout(options.timeout)
        self._request_sent = False
        token = options.token
        if token and any(ord(char) < 32 or 127 <= ord(char) <= 159 or ord(char) > 255 for char in token):
            raise self._client_error("The token contains characters an HTTP header cannot carry")
        self._opener = _request.build_opener(
            _request.ProxyHandler({}),
            _NoRedirect(),
            _TimeoutHTTPHandler(self.timeout, self._mark_request_sent),
            _TimeoutHTTPSHandler(self.timeout, self._mark_request_sent),
        )

    def get(self, path: str) -> Any:
        return self.get_result(path).payload

    def get_result(self, path: str) -> ToolResult:
        return self._get_result(path)

    def invoke(self, tool: str, arguments: dict[str, Any]) -> ToolResult:
        return self._invoke(tool, arguments)

    def catalog(self) -> dict[str, Any]:
        return self.catalog_result().payload

    def catalog_result(self) -> ToolResult:
        return self._catalog_result()

    def post(self, path: str, body: str) -> Any:
        return self.post_result(path, body).payload

    def post_result(self, path: str, body: str) -> ToolResult:
        endpoint = self._endpoint(path)
        status, response = self._send(endpoint, "POST", body)
        if not 200 <= status < 300:
            raise self._describe_failure(status, response)
        try:
            payload = _parse_json(response, endpoint, status) if response.strip() else None
            return ToolResult(path, status, response, payload)
        except ClientError as error:
            raise self._client_error(str(error), status=status, body=response, request_sent=True) from None

    def _get_result(self, path: str) -> ToolResult:
        endpoint = self._endpoint(path)
        status, body = self._send(endpoint, "GET", None)
        if not 200 <= status < 300:
            raise self._describe_failure(status, body)
        try:
            return ToolResult(path, status, body, _parse_json(body, endpoint, status))
        except ClientError as error:
            raise self._client_error(str(error)) from None

    def _invoke(self, tool: str, arguments: dict[str, Any]) -> ToolResult:
        path = f"/cli/tools/{quote(tool, safe='')}"
        endpoint = self._endpoint(path)
        status, body = self._send(endpoint, "POST", arguments)
        if not 200 <= status < 300:
            return ToolResult(tool, status, body, _optional_json(body))
        try:
            payload = _parse_json(body, endpoint, status)
        except ClientError as error:
            raise self._client_error(str(error)) from None
        return ToolResult(tool, status, body, payload)

    def _catalog_result(self) -> ToolResult:
        path = "/cli"
        endpoint = self._endpoint(path)
        status, body = self._send(endpoint, "GET", None)
        if status == 404:
            raise self._client_error(
                f"No sharpit command-line endpoint at {endpoint}. The application may predate it, "
                "be running sharpit at a different --api-path, or not be a sharpit application."
            )
        if not 200 <= status < 300:
            raise self._describe_failure(status, body)
        try:
            payload = _parse_json(body, endpoint, status)
        except ClientError as error:
            raise self._client_error(str(error)) from None
        catalog = cast(JsonObject, payload) if isinstance(payload, dict) else None
        if (
            catalog is None
            or catalog.get("serverName") != "sharpit"
            or not isinstance(catalog.get("enabled"), bool)
            or not isinstance(catalog.get("tools"), list)
            or (not catalog["enabled"] and catalog["tools"])
        ):
            raise self._client_error(
                "Response is not a sharpit catalog: expected serverName 'sharpit', a boolean enabled, "
                "and a tools array that is empty while disabled."
            )
        return ToolResult(path, status, body, catalog)

    def _send(
        self,
        endpoint: str,
        method: str,
        arguments: dict[str, Any] | str | None,
    ) -> tuple[int, str]:
        self._validate_url(endpoint)
        base = self.options.base_url.rstrip("/")
        deadline = time.monotonic() + self.timeout
        try:
            outgoing = self._request(endpoint, method, arguments)
        except ValueError:
            raise self._client_error("Request could not be encoded for HTTP") from None
        outcome = self._exchange(outgoing, deadline, base)
        status, body = outcome
        if not 200 <= status < 300:
            return status, body.decode("utf-8", errors="replace")
        return status, self._decode_body(body, status)

    def _exchange(self, outgoing: Any, deadline: float, base: str) -> tuple[int, bytes]:
        self._request_sent = False
        result: list[tuple[int, bytes] | Exception] = []

        def perform() -> None:
            try:
                with self._open_response(outgoing, min(self.timeout, _CONNECT_TIMEOUT)) as response:
                    status = cast(int, getattr(response, "status", getattr(response, "code", 0)))
                    sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
                    if sock is not None:
                        sock.settimeout(max(0.0, deadline - time.monotonic()))
                    result.append((status, response.read()))
            except Exception as error:
                result.append(error)

        worker = threading.Thread(target=perform, daemon=True)
        worker.start()
        worker.join(max(0.0, deadline - time.monotonic()))
        if worker.is_alive():
            raise self._timeout_error(base, self.timeout, request_sent=self._request_sent)
        outcome = result[0]
        if isinstance(outcome, Exception):
            if isinstance(outcome, ClientError):
                raise outcome
            raise self._request_error(outcome, base, request_sent=self._request_sent) from outcome
        return outcome

    def _request_error(self, error: Exception, base: str, *, request_sent: bool = False) -> ClientError:
        if isinstance(error, ClientError):
            return error
        if isinstance(error, TimeoutError):
            return self._timeout_error(base, self.timeout, request_sent=request_sent)
        if isinstance(error, (_http_client.HTTPException, OSError)):
            return self._transport_error(error, base, request_sent=request_sent)
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

    def _request(self, endpoint: str, method: str, arguments: dict[str, Any] | str | None) -> Any:
        headers = {"Accept": "application/json", "User-Agent": f"sharpit/{__version__}"}
        data = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            data = (arguments if isinstance(arguments, str) else json.dumps(arguments or {})).encode("utf-8")
        if self.options.token:
            headers["Authorization"] = f"Bearer {self.options.token}"
        return _request.Request(endpoint, data=data, headers=headers, method=method)  # noqa: S310

    def _open_response(self, outgoing: Any, timeout: float) -> Any:
        try:
            return self._opener.open(outgoing, timeout=timeout)
        except _request.HTTPError as error:
            if error.code in (301, 302, 303, 307, 308):
                error.close()
                raise self._client_error(
                    f"Request was redirected (HTTP {error.code})", request_sent=self._request_sent
                ) from None
            return error
        except TimeoutError as error:
            raise self._timeout_error(
                self.options.base_url.rstrip("/"), self.timeout, request_sent=self._request_sent
            ) from error
        except OSError as error:
            if _is_tls_error(error):
                raise self._client_error(
                    f"TLS request to {self.options.base_url.rstrip('/')} failed: {error}",
                    request_sent=self._request_sent,
                ) from error
            raise self._client_error(
                _cannot_reach(self.options.base_url.rstrip("/")), request_sent=self._request_sent
            ) from error

    def _transport_error(self, error: Exception, base: str, *, request_sent: bool = False) -> ClientError:
        if isinstance(error, OSError):
            if _is_tls_error(error):
                return self._client_error(f"TLS request to {base} failed: {error}", request_sent=request_sent)
            return self._client_error(_cannot_reach(base), request_sent=request_sent)
        return self._client_error(f"Request to {base} failed: {error}", request_sent=request_sent)

    def _decode_body(self, body: bytes, status: int | None = None) -> str:
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            raise self._client_error("Response is not valid UTF-8", status=status, request_sent=True) from None

    def _timeout_error(self, base: str, timeout: float, *, request_sent: bool = False) -> ClientError:
        duration = f"{timeout * 1000:g}ms" if timeout < 1 else f"{timeout:g}s"
        return self._client_error(
            f"No response from {base} within {duration}. Raise --timeout if the tool is expected to be slow.",
            request_sent=request_sent,
        )

    def _describe_failure(self, status: int, body: str) -> ClientError:
        document = error_body(body)
        error = _nonblank(document.get("error"))
        reason = _nonblank(document.get("reason"))
        message = _nonblank(document.get("message"))
        panel = _nonblank(document.get("panel"))

        specific = reason or message
        detail = f": {error}" if error else ""
        if specific and specific != error:
            detail += f": {specific}"
        panel_refusal = status == 403 and panel is not None and reason is not None and error == _PANEL_ACCESS_DENIED
        if status == 401 or (status == 403 and not panel_refusal):
            text = (
                f"sharpit refused the request (HTTP {status}){detail}. A non-loopback --url needs --token "
                "or SHARPIT_TOKEN, "
                "and sharpit only answers requests it considers local."
            )
        else:
            text = f"sharpit answered HTTP {status}{detail}"
        return self._client_error(text, status=status, body=body)

    def _endpoint(self, path: str) -> str:
        base = self.options.base_url.rstrip("/")
        api = self.options.api_path.rstrip("/")
        return f"{base}{api}{path if path.startswith('/') else '/' + path}"

    def _client_error(
        self,
        message: str,
        *,
        status: int | None = None,
        body: str = "",
        request_sent: bool = False,
    ) -> ClientError:
        return ClientError(
            safe_text(message, self.options.token),
            status=status,
            body=safe_text(body, self.options.token),
            request_sent=request_sent,
        )

    def _mark_request_sent(self) -> None:
        self._request_sent = True


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


def error_body(body: Any) -> dict[str, Any]:
    if isinstance(body, dict):
        return cast(JsonObject, body)
    if isinstance(body, str):
        try:
            parsed = _strict_json(body)
            return cast(JsonObject, parsed) if isinstance(parsed, dict) else {}
        except (ValueError, ClientError):
            pass
    return {}


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


def _redact(text: str, token: str | None) -> str:
    if token:
        redacted_json = False

        def redact_json_string(match: re.Match[str]) -> str:
            nonlocal redacted_json
            raw = match.group()
            try:
                value = json.loads(raw)
            except ValueError:
                return raw
            if isinstance(value, str) and token in value:
                redacted_json = True
                return json.dumps(value.replace(token, "[redacted]"), ensure_ascii="\\u" in raw.lower())
            return raw

        text = re.sub(r'"(?:\\.|[^"\\])*"', redact_json_string, text)
        if redacted_json:
            return text
        text = text.replace(f"Authorization: Bearer {token}", "[redacted]")
        text = text.replace(f"Bearer {token}", "Bearer [redacted]").replace(token, "[redacted]")
    return text


def safe_text(text: str, token: str | None) -> str:
    return _redact(_sharpit_text(text), _sharpit_text(token) if token else None)


def _cannot_reach(base: str) -> str:
    return f"Cannot reach sharpit at {base}. Is the application running, and is that the right --url?"


def _is_tls_error(error: BaseException) -> bool:
    reason = getattr(error, "reason", None)
    return (
        type(error).__module__ in {"ssl", "_ssl"}
        or type(error).__name__.startswith("SSL")
        or type(reason).__module__ in {"ssl", "_ssl"}
        or type(reason).__name__.startswith("SSL")
    )


def _valid_timeout(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return 60.0
    return timeout if 0 < timeout < float("inf") else 60.0
