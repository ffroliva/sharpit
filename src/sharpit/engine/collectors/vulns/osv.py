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

import http.client
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from sharpit.engine.collectors.vulns.deadline import SCAN_DEADLINE_EXCEEDED, ScanDeadline
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
    complete: set[Package]  # every page fetched (BootUI completedPackages)


def request_json(
    opener: Opener,
    request: urllib.request.Request,
    timeout: float,
    max_bytes: int,
    what: str,
    deadline: ScanDeadline | None = None,
) -> Any:
    """Send ``request`` and parse its JSON body; any failure raises ``OsvError``."""
    try:
        with opener.open(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            body = _read_bounded_body(response, timeout, max_bytes, deadline)
    except OsvError:
        raise
    except urllib.error.HTTPError as error:
        raise OsvError(f"{what} returned HTTP {error.code}") from error
    except (OSError, ValueError, http.client.HTTPException) as error:  # URLError, timeouts, IncompleteRead...
        raise OsvError(f"{what} failed ({type(error).__name__})") from error
    if status < 200 or status >= 300:
        raise OsvError(f"{what} returned HTTP {status}")
    if len(body) > max_bytes:
        raise OsvError(f"Response body exceeds {max_bytes} bytes")
    try:
        return json.loads(body)
    except (ValueError, RecursionError) as error:  # JSONDecodeError, UnicodeDecodeError, deeply nested arrays
        raise OsvError(f"{what} returned malformed JSON") from error


def _read_bounded_body(response: Any, timeout: float, max_bytes: int, deadline: ScanDeadline | None) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        remaining = deadline.remaining() if deadline is not None else timeout
        if deadline is not None and remaining <= 0:
            raise OsvError(SCAN_DEADLINE_EXCEEDED)
        sock = getattr(getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None), "settimeout", None)
        if sock is not None:
            sock(min(timeout, remaining))
        chunk = cast(bytes, response.read1(min(64 * 1024, max_bytes + 1 - size)))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > max_bytes:
            break
        if deadline is not None and deadline.check_expired():
            raise OsvError(SCAN_DEADLINE_EXCEEDED)
    return b"".join(chunks)


def is_request_timeout(error: OsvError) -> bool:
    cause = error.__cause__
    return isinstance(cause, TimeoutError) or isinstance(getattr(cause, "reason", None), TimeoutError)


class OsvClient:
    def __init__(self, base_uri: str, timeout: float, opener: Opener | None = None) -> None:
        self._base_uri = base_uri.rstrip("/") + "/"  # joined with relative paths, so a base path is kept
        self._timeout = timeout
        self._opener = opener

    def _open(self) -> Opener:
        if self._opener is None:
            self._opener = urllib.request.build_opener()
        return self._opener

    def querybatch(self, pkgs: Sequence[Package], deadline: ScanDeadline | None = None) -> QueryResult:
        """Query OSV in chunks of 1000. A failure before any chunk completed raises ``OsvError``; a later failure
        puts that chunk's unfinished packages and every later package in ``failed`` (BootUI ``queryBatch``)."""
        result = QueryResult({}, [], False, set())
        for start in range(0, len(pkgs), MAX_QUERYBATCH_SIZE):
            if start and deadline is not None and deadline.check_expired():
                result.failed = list(pkgs[start:])
                break
            chunk = list(pkgs[start : start + MAX_QUERYBATCH_SIZE])
            try:
                ids, failed, truncated, complete = self._query_chunk(chunk, deadline)
            except OsvError:
                if start == 0:
                    raise
                result.failed = list(pkgs[start:])
                break
            result.ids.update(ids)
            result.truncated |= truncated
            result.complete |= complete
            if failed:
                result.failed = failed + list(pkgs[start + len(chunk) :])
                break
        return result

    def _query_chunk(
        self, chunk: list[Package], deadline: ScanDeadline | None = None
    ) -> tuple[dict[Package, list[str]], list[Package], bool, set[Package]]:
        ids: dict[Package, list[str]] = {pkg: [] for pkg in chunk}
        seen: dict[Package, set[str]] = {pkg: set() for pkg in chunk}
        complete: set[Package] = set()
        pending: list[tuple[Package, str | None]] = [(pkg, None) for pkg in chunk]
        for page in range(MAX_QUERY_BATCH_PAGES):
            if page and deadline is not None and deadline.check_expired():
                return ids, [pkg for pkg, _ in pending], False, complete
            try:
                results = self._query_page(pending, deadline)
            except OsvError:
                if page == 0:
                    raise
                return ids, [pkg for pkg, _ in pending], False, complete
            pending = self._record_page(pending, results, ids, seen, complete)
            if not pending:
                return ids, [], False, complete
        return ids, [], True, complete

    @staticmethod
    def _record_page(
        pending: list[tuple[Package, str | None]],
        results: list[dict[str, Any]],
        ids: dict[Package, list[str]],
        seen: dict[Package, set[str]],
        complete: set[Package],
    ) -> list[tuple[Package, str | None]]:
        next_pending: list[tuple[Package, str | None]] = []
        for (pkg, _), item in zip(pending, results, strict=True):
            for vuln in cast(list[dict[str, Any]], item.get("vulns") or []):
                vuln_id = cast(str, vuln["id"])
                if vuln_id not in seen[pkg]:
                    seen[pkg].add(vuln_id)
                    ids[pkg].append(vuln_id)
            token = text_field(item, "next_page_token")
            if token is None:
                complete.add(pkg)
            else:
                next_pending.append((pkg, token))
        return next_pending

    def _query_page(
        self, pending: list[tuple[Package, str | None]], deadline: ScanDeadline | None = None
    ) -> list[dict[str, Any]]:
        queries: list[dict[str, Any]] = []
        for pkg, token in pending:
            query: dict[str, Any] = {"package": {"name": pkg.name, "ecosystem": ECOSYSTEM}, "version": pkg.version}
            if token is not None:
                query["page_token"] = token
            queries.append(query)
        request = urllib.request.Request(
            urllib.parse.urljoin(self._base_uri, "v1/querybatch"),
            data=json.dumps({"queries": queries}, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            budget = deadline.request_budget(self._timeout) if deadline is not None else None
        except TimeoutError as error:
            raise OsvError(SCAN_DEADLINE_EXCEEDED) from error
        try:
            root = request_json(
                self._open(),
                request,
                budget.timeout if budget else self._timeout,
                QUERYBATCH_MAX_BYTES,
                "OSV query",
                deadline,
            )
        except OsvError as error:
            if deadline is not None and (
                deadline.check_expired()
                or (budget is not None and budget.capped_by_deadline and is_request_timeout(error))
            ):
                deadline.mark_expired()
                raise OsvError(SCAN_DEADLINE_EXCEEDED) from error
            raise
        if deadline is not None and deadline.check_expired():
            deadline.mark_expired()
            raise OsvError(SCAN_DEADLINE_EXCEEDED)
        return _validate_results(root, len(pending))

    def vuln(self, id: str, deadline: ScanDeadline | None = None) -> dict[str, Any]:
        """``GET /v1/vulns/{id}``; any failure, or a body that is not a JSON object, raises ``OsvError``."""
        url = urllib.parse.urljoin(self._base_uri, "v1/vulns/" + urllib.parse.quote(id, safe=""))
        try:
            budget = deadline.request_budget(self._timeout) if deadline is not None else None
        except TimeoutError as error:
            raise OsvError(SCAN_DEADLINE_EXCEEDED) from error
        try:
            doc = request_json(
                self._open(),
                urllib.request.Request(url, method="GET"),
                budget.timeout if budget else self._timeout,
                ADVISORY_MAX_BYTES,
                f"OSV advisory {id}",
                deadline,
            )
        except OsvError as error:
            if deadline is not None and (
                deadline.check_expired()
                or (budget is not None and budget.capped_by_deadline and is_request_timeout(error))
            ):
                deadline.mark_expired()
                raise OsvError(SCAN_DEADLINE_EXCEEDED) from error
            raise
        if deadline is not None and deadline.check_expired():
            deadline.mark_expired()
            raise OsvError(SCAN_DEADLINE_EXCEEDED)
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
                if not isinstance(vuln, dict) or text_field(cast(dict[str, Any], vuln), "id") is None:
                    raise OsvError("OSV querybatch returned a vulnerability without a non-blank id")
        token = result.get("next_page_token")
        if token is not None and not isinstance(token, str):
            raise OsvError("OSV querybatch returned a non-string next_page_token")
    return cast(list[dict[str, Any]], items)


def text_field(node: dict[str, Any], key: str) -> str | None:
    """BootUI ``text``: a non-blank string field, else None."""
    value = node.get(key)
    return value if isinstance(value, str) and value.strip() else None
