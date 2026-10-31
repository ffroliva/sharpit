"""FIRST.org EPSS client (port of BootUI ``OsvVulnerabilityScanner.fetchEpssChunk``/``fetchEpssPage`` and the
``DependencyReports`` CVE helpers).

EPSS is best effort: ``scores`` never raises. On any failure (transport, status, body, row or pagination validation)
it stops, keeps the scores gathered so far and sets ``failed``, like BootUI ``applyEpss``; callers can then tell
"enrichment was incomplete or unavailable" from "no available data".
"""

from __future__ import annotations

import math
import re
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from sharpit.engine.collectors.vulns.osv import MAX_QUERY_BATCH_PAGES, Opener, OsvError, request_json

CVE_PARAMETER_MAX_LENGTH = 2000  # FIRST.org's documented limit on the comma-joined cve parameter
EPSS_MAX_BYTES = 1024 * 1024
_CVE_ID = re.compile(r"CVE-[0-9]{4}-[0-9]{4,}")


class _EpssError(Exception):
    pass


@dataclass
class EpssResult:
    scores: dict[str, tuple[float, float]]  # CVE id -> (probability, percentile)
    failed: bool  # enrichment stopped early; ``scores`` holds what was gathered before the failure


def canonical_cve_id(value: str | None) -> str | None:
    """Upper-case trimmed CVE id, or None when malformed."""
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized if _CVE_ID.fullmatch(normalized) else None


def epss_cve_chunks(cve_ids: Sequence[str]) -> list[list[str]]:
    """Distinct canonical CVE ids in order, split so each comma-joined chunk stays within 2000 characters."""
    chunks: list[list[str]] = []
    chunk: list[str] = []
    length = 0
    seen: set[str] = set()
    for value in cve_ids:
        cve = canonical_cve_id(value)
        if cve is None or cve in seen or len(cve) > CVE_PARAMETER_MAX_LENGTH:
            continue
        seen.add(cve)
        added = len(cve) + (1 if chunk else 0)
        if chunk and length + added > CVE_PARAMETER_MAX_LENGTH:
            chunks.append(chunk)
            chunk, length, added = [], 0, len(cve)
        chunk.append(cve)
        length += added
    if chunk:
        chunks.append(chunk)
    return chunks


class EpssClient:
    def __init__(self, base_uri: str, timeout: float, opener: Opener | None = None) -> None:
        self._base_uri = base_uri.rstrip("/") + "/"  # joined with relative paths, so a base path is kept
        self._timeout = timeout
        self._opener = opener

    def _open(self) -> Opener:
        if self._opener is None:
            self._opener = urllib.request.build_opener()
        return self._opener

    def scores(self, cve_ids: Sequence[str]) -> EpssResult:
        """Scores for the CVEs EPSS has data on; never raises (BootUI ``applyEpss``)."""
        scores: dict[str, tuple[float, float]] = {}
        try:
            for chunk in epss_cve_chunks(cve_ids):
                self._fetch_chunk(chunk, scores)
        except (OsvError, _EpssError):
            return EpssResult(scores, failed=True)
        return EpssResult(scores, failed=False)

    def _fetch_chunk(self, cve_ids: list[str], scores: dict[str, tuple[float, float]]) -> None:
        requested = set(cve_ids)
        seen: set[str] = set()
        offset = 0
        expected_total: int | None = None
        for _ in range(min(MAX_QUERY_BATCH_PAGES, len(cve_ids))):
            root = self._fetch_page(cve_ids, offset)
            data = cast(list[Any], root["data"])
            invalid = False
            for row in data:
                entry = cast(dict[str, Any], row) if isinstance(row, dict) else {}
                cve = canonical_cve_id(_text(entry, "cve"))
                probability, percentile = _probability(entry, "epss"), _probability(entry, "percentile")
                if cve is None or cve not in requested or cve in seen or probability is None or percentile is None:
                    invalid = True  # BootUI keeps the page's valid rows, then fails
                    continue
                seen.add(cve)
                scores[cve] = (probability, percentile)
            if invalid:
                raise _EpssError("EPSS returned invalid, duplicate or unrequested score rows")
            if not {"total", "offset", "limit"} & root.keys():
                if expected_total is not None:
                    raise _EpssError("EPSS continuation omitted pagination metadata")
                return
            total, returned_offset, limit = (_integer(root, key) for key in ("total", "offset", "limit"))
            if (
                total > len(requested)
                or returned_offset != offset
                or limit < 1
                or limit > len(requested)
                or len(data) > limit
                or offset + len(data) > total
                or (expected_total is not None and total != expected_total)
            ):
                raise _EpssError("EPSS returned inconsistent pagination metadata")
            expected_total = total
            offset += len(data)
            if offset == total:
                return
            if not data:
                raise _EpssError("EPSS pagination made no progress")
        raise _EpssError("EPSS pagination exceeded its safety bound")

    def _fetch_page(self, cve_ids: list[str], offset: int) -> dict[str, Any]:
        query = f"cve={','.join(cve_ids)}&limit={len(cve_ids)}&offset={offset}"
        request = urllib.request.Request(urllib.parse.urljoin(self._base_uri, "data/v1/epss?" + query), method="GET")
        root = request_json(self._open(), request, self._timeout, EPSS_MAX_BYTES, "EPSS query")
        if not isinstance(root, dict) or not isinstance(cast(dict[str, Any], root).get("data"), list):
            raise _EpssError("EPSS response did not contain a data array")
        return cast(dict[str, Any], root)


def _probability(entry: dict[str, Any], key: str) -> float | None:
    """A string field parsed as a finite float in 0..1 (BootUI reads ``epss``/``percentile`` as text only)."""
    text = _text(entry, key)
    if text is None:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) and 0.0 <= value <= 1.0 else None


def _integer(root: dict[str, Any], key: str) -> int:
    value = root.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 2**31 - 1:
        raise _EpssError(f"EPSS returned invalid {key} metadata")
    return value


def _text(node: dict[str, Any], key: str) -> str | None:
    value = node.get(key)
    return value if isinstance(value, str) and value.strip() else None
