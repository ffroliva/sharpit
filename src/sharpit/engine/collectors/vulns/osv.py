"""OSV.dev client (port of the transport half of BootUI ``OsvVulnerabilityScanner``: ``queryBatch``,
``queryBatchChunk``, ``queryBatchRequest`` and ``fetchVulnerability``).

Only the stdlib ``urllib`` is used. Every request carries the configured timeout and nothing retries. The opener is
injectable for tests and is built lazily, never at import or definition time.

Dropped from ``OsvVulnerabilityScannerTests`` (JVM/adapter-only): ``singleArgConstructorUsesConfiguredOsvBaseUri``
(Spring property binding), ``fetchesManyDistinctAdvisoriesConcurrentlyWithoutLosingOrMisattributingAny`` and
``countsConcurrentAdvisoryFetchFailuresCorrectlyAcrossTheBoundedPool`` (the 10-thread fetch pool lives in Task 12's
scan service; this client fetches one advisory per call),
``completedNoMatchEvidenceDoesNotClaimCompleteInventoryCoverage`` (jar-archive coverage has no PyPI counterpart).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from sharpit.engine.collectors.vulns.inventory import Package

ECOSYSTEM = "PyPI"
MAX_QUERYBATCH_SIZE = 1000  # OSV.dev rejects larger batches with HTTP 400
MAX_QUERY_BATCH_PAGES = 20  # bound on next_page_token rounds per chunk
QUERYBATCH_MAX_BYTES = 5 * 1024 * 1024
ADVISORY_MAX_BYTES = 1024 * 1024


class Opener(Protocol):
    def open(self, fullurl: urllib.request.Request, data: Any = ..., timeout: float | None = ...) -> Any: ...


class OsvError(Exception):
    """An OSV request failed: transport error, timeout, non-2xx status, oversized or malformed body."""


@dataclass
class QueryResult:
    ids: dict[Package, list[str]]  # every queried package -> its distinct advisory ids, in OSV order
    failed: list[Package]  # packages whose query did not complete (a failed page or chunk)
    truncated: bool  # some query still had a next_page_token after MAX_QUERY_BATCH_PAGES rounds


def request_json(opener: Opener, request: urllib.request.Request, timeout: float, max_bytes: int, what: str) -> Any:
    """Send ``request`` and parse its JSON body; any failure raises ``OsvError``."""
    try:
        with opener.open(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            body = cast(bytes, response.read(max_bytes + 1))
    except urllib.error.HTTPError as error:
        raise OsvError(f"{what} returned HTTP {error.code}") from error
    except (OSError, ValueError) as error:  # URLError, timeouts, resets, bad URLs
        raise OsvError(f"{what} failed ({type(error).__name__})") from error
    if status < 200 or status >= 300:
        raise OsvError(f"{what} returned HTTP {status}")
    if len(body) > max_bytes:
        raise OsvError(f"Response body exceeds {max_bytes} bytes")
    try:
        return json.loads(body)
    except ValueError as error:  # JSONDecodeError and UnicodeDecodeError
        raise OsvError(f"{what} returned malformed JSON") from error


class OsvClient:
    def __init__(self, base_uri: str, timeout: float, opener: Opener | None = None) -> None:
        self._base_uri = base_uri
        self._timeout = timeout
        self._opener = opener

    def _open(self) -> Opener:
        if self._opener is None:
            self._opener = urllib.request.build_opener()
        return self._opener

    def querybatch(self, pkgs: Sequence[Package]) -> QueryResult:
        """Query OSV in chunks of 1000. A failure before any chunk completed raises ``OsvError``; a later failure
        puts that chunk's unfinished packages and every later package in ``failed`` (BootUI ``queryBatch``)."""
        result = QueryResult({}, [], False)
        for start in range(0, len(pkgs), MAX_QUERYBATCH_SIZE):
            chunk = list(pkgs[start : start + MAX_QUERYBATCH_SIZE])
            try:
                ids, failed, truncated = self._query_chunk(chunk)
            except OsvError:
                if start == 0:
                    raise
                result.failed = list(pkgs[start:])
                break
            result.ids.update(ids)
            result.truncated |= truncated
            if failed:
                result.failed = failed + list(pkgs[start + len(chunk) :])
                break
        return result

    def _query_chunk(self, chunk: list[Package]) -> tuple[dict[Package, list[str]], list[Package], bool]:
        ids: dict[Package, list[str]] = {pkg: [] for pkg in chunk}
        pending: list[tuple[Package, str | None]] = [(pkg, None) for pkg in chunk]
        for page in range(MAX_QUERY_BATCH_PAGES):
            try:
                results = self._query_page(pending)
            except OsvError:
                if page == 0:
                    raise
                return ids, [pkg for pkg, _ in pending], False
            next_pending: list[tuple[Package, str | None]] = []
            for (pkg, _), item in zip(pending, results, strict=True):
                for vuln in cast(list[dict[str, Any]], item.get("vulns") or []):
                    vuln_id = cast(str, vuln["id"])
                    if vuln_id not in ids[pkg]:
                        ids[pkg].append(vuln_id)
                token = _text(item, "next_page_token")
                if token is not None:
                    next_pending.append((pkg, token))
            pending = next_pending
            if not pending:
                return ids, [], False
        return ids, [], True

    def _query_page(self, pending: list[tuple[Package, str | None]]) -> list[dict[str, Any]]:
        queries: list[dict[str, Any]] = []
        for pkg, token in pending:
            query: dict[str, Any] = {"package": {"name": pkg.name, "ecosystem": ECOSYSTEM}, "version": pkg.version}
            if token is not None:
                query["page_token"] = token
            queries.append(query)
        request = urllib.request.Request(
            urllib.parse.urljoin(self._base_uri, "/v1/querybatch"),
            data=json.dumps({"queries": queries}, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        root = request_json(self._open(), request, self._timeout, QUERYBATCH_MAX_BYTES, "OSV query")
        return _validate_results(root, len(pending))

    def vuln(self, id: str) -> dict[str, Any]:
        """``GET /v1/vulns/{id}``; any failure, or a body that is not a JSON object, raises ``OsvError``."""
        url = urllib.parse.urljoin(self._base_uri, "/v1/vulns/" + urllib.parse.quote(id, safe=""))
        doc = request_json(
            self._open(),
            urllib.request.Request(url, method="GET"),
            self._timeout,
            ADVISORY_MAX_BYTES,
            f"OSV advisory {id}",
        )
        if not isinstance(doc, dict):
            raise OsvError(f"OSV advisory {id} is not a JSON object")
        return cast(dict[str, Any], doc)


def _validate_results(root: Any, expected: int) -> list[dict[str, Any]]:
    results = cast(dict[str, Any], root).get("results") if isinstance(root, dict) else None
    if not isinstance(results, list):
        raise OsvError("OSV querybatch response did not contain a results array")
    items = cast(list[Any], results)
    if len(items) != expected:
        raise OsvError(f"OSV querybatch returned {len(items)} results for {expected} queries")
    for item in items:
        if not isinstance(item, dict):
            raise OsvError("OSV querybatch returned a non-object result")
        result = cast(dict[str, Any], item)
        if "vulns" in result:
            vulns = result["vulns"]
            if not isinstance(vulns, list):
                raise OsvError("OSV querybatch returned a non-array vulns field")
            for vuln in cast(list[Any], vulns):
                if not isinstance(vuln, dict) or _text(cast(dict[str, Any], vuln), "id") is None:
                    raise OsvError("OSV querybatch returned a vulnerability without a non-blank id")
        token = result.get("next_page_token")
        if token is not None and not isinstance(token, str):
            raise OsvError("OSV querybatch returned a non-string next_page_token")
    return cast(list[dict[str, Any]], items)


def _text(node: dict[str, Any], key: str) -> str | None:
    value = node.get(key)
    return value if isinstance(value, str) and value.strip() else None
