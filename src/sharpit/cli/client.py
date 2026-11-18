"""HTTP client for a running sharpit application."""

from __future__ import annotations

import http.client as http_client
import json
import time
from typing import Any
from urllib import request
from urllib.parse import urlsplit

from sharpit import __version__

_MAX_RESPONSE_BYTES = 1_048_576


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        return None


class ClientError(Exception):
    """A safe-to-display CLI transport failure."""


class Client:
    def __init__(self, options: Any) -> None:
        self.options = options
        self._opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())

    def get(self, path: str) -> Any:
        return self._send(path, "GET")

    def invoke(self, tool: str, arguments: dict[str, Any]) -> Any:
        return self._send(f"/cli/tools/{tool}", "POST", arguments)

    def catalog(self) -> Any:
        return self.get("/cli")

    def _send(self, path: str, method: str, arguments: dict[str, Any] | None = None) -> Any:
        base = self.options.base_url.rstrip("/")
        api = self.options.api_path.rstrip("/")
        url = f"{base}{api}{path if path.startswith('/') else '/' + path}"
        if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
            raise ClientError("The API URL must use HTTP or HTTPS")
        headers = {"Accept": "application/json", "User-Agent": f"sharpit/{__version__}"}
        data = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            data = json.dumps(arguments or {}).encode("utf-8")
        if self.options.token:
            headers["Authorization"] = f"Bearer {self.options.token}"
        timeout = float(self.options.timeout)
        deadline = time.monotonic() + timeout
        try:
            outgoing = request.Request(url, data=data, headers=headers, method=method)  # noqa: S310
            response = self._opener.open(outgoing, timeout=timeout)
            with response:
                body = _read_bounded(response, deadline)
                status = response.status
        except request.HTTPError as error:
            if error.code in (301, 302, 303, 307, 308):
                raise ClientError(f"Request was redirected (HTTP {error.code})") from None
            raise ClientError(f"Request failed with HTTP {error.code}") from None
        except (request.URLError, http_client.HTTPException, TimeoutError, OSError):  # type: ignore[attr-defined]
            raise ClientError("Request failed; check --url and --timeout") from None
        if status < 200 or status >= 300:
            raise ClientError(f"Request failed with HTTP {status}")
        return _parse_json(body)


def _read_bounded(response: Any, deadline: float) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ClientError("Request exceeded its timeout")
        if response.fp and response.fp.raw:
            response.fp.raw._sock.settimeout(remaining)
        chunk = response.read1(min(65536, _MAX_RESPONSE_BYTES + 1 - total))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > _MAX_RESPONSE_BYTES:
            raise ClientError("Response exceeded the 1048576 byte limit")
        chunks.append(chunk)


def _parse_json(body: bytes) -> Any:
    try:
        return json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ClientError("Response was not valid strict JSON") from None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError(f"invalid JSON constant: {value}")
