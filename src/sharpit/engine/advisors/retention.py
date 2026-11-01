"""Per-scan violation retention and paging (port of BootUI ``AdvisorScanState``, ``AdvisorViolationCollector`` and
``AdvisorViolationException``). Only the latest scan is kept; reading never scans."""

from __future__ import annotations

import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sharpit.engine.paging import paged

DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 1000
_INTEGER = re.compile(r"-?[0-9]+")


class AdvisorViolationError(Exception):
    """BootUI ``AdvisorViolationException``: the web layer renders ``status {"error": message}``."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def parse_integer(raw: str | None, name: str) -> int | None:
    """An optional REST paging parameter (``AdvisorViolationException.parseInteger``); range checks are ``page``'s."""
    if raw is None:
        return None
    word = name if name in ("offset", "limit") else "parameter"
    value = int(raw) if _INTEGER.fullmatch(raw) else None
    if value is None or not -(2**31) <= value < 2**31:
        raise AdvisorViolationError(400, f"Advisor violation {word} must be a valid 32-bit integer.")
    return value


@dataclass(frozen=True)
class _Scan:
    scan_id: str
    total: int
    retained: int
    rules: dict[str, tuple[int, tuple[str, ...], tuple[str, ...] | None]]  # id -> (count, details, fingerprints)


class ViolationRetention:
    def __init__(self, max_retained: int) -> None:
        if max_retained <= 0:
            raise ValueError("Advisor violation retention limit must be positive.")
        self.max_retained = max_retained
        self._scan: _Scan | None = None  # replaced whole, so a reader always sees one consistent scan

    def store(
        self, results: Mapping[str, Sequence[str]], fingerprints: Mapping[str, Sequence[str]] | None = None
    ) -> str:
        """Index every rule's violation strings (in order, up to ``max_retained`` across rules) as the new scan.

        ``fingerprints`` (sharpit-only, 0.3.0 spec §14) maps a rule id to one fingerprint per violation, in the same
        order; pages of a scan stored with it carry a parallel ``fingerprints`` list."""
        rules: dict[str, tuple[int, tuple[str, ...], tuple[str, ...] | None]] = {}
        total = retained = 0
        for rule_id, violations in results.items():
            if not violations:
                continue  # BootUI record() skips a rule with no violations
            kept = tuple(violations[: self.max_retained - retained])
            kept_fingerprints = None if fingerprints is None else tuple(fingerprints.get(rule_id, ()))[: len(kept)]
            rules[rule_id] = (len(violations), kept, kept_fingerprints)
            total += len(violations)
            retained += len(kept)
        scan = _Scan(secrets.token_hex(8), total, retained, rules)
        self._scan = scan
        return scan.scan_id

    def details(self) -> dict[str, Any]:
        """``AdvisorViolationDetailsDto`` of the latest scan, ``unknown()`` before the first one."""
        scan = self._scan
        if scan is None:
            return {"scanId": None, "total": 0, "retained": 0, "retentionLimit": 0, "truncated": False}
        return {
            "scanId": scan.scan_id,
            "total": scan.total,
            "retained": scan.retained,
            "retentionLimit": self.max_retained,
            "truncated": scan.retained < scan.total,
        }

    def page(
        self, scan_id: str | None, rule_id: str | None, offset: int | None, limit: int | None, max_results: int
    ) -> dict[str, Any]:
        """``AdvisorRuleViolationsDto``; ``limit`` defaults to 100 and is capped at ``min(1000, max_results)``."""
        if not rule_id or not rule_id.strip():
            raise AdvisorViolationError(400, "Advisor rule ID must not be blank.")
        if not scan_id or not scan_id.strip():
            raise AdvisorViolationError(400, "Advisor scan ID must not be blank.")
        if offset is not None and offset < 0:
            raise AdvisorViolationError(400, "Advisor violation offset must not be negative.")
        if limit is not None and limit <= 0:
            raise AdvisorViolationError(400, "Advisor violation limit must be positive.")
        scan = self._scan
        if scan is None:
            raise AdvisorViolationError(
                409, "No completed advisor scan is available. Reread the cached report before requesting details."
            )
        if scan.scan_id != scan_id:
            raise AdvisorViolationError(
                409, "Advisor scan has been replaced. Reread the cached report before requesting details."
            )
        rule = scan.rules.get(rule_id)
        if rule is None:
            raise AdvisorViolationError(404, "Advisor rule has no findings in the current scan.")
        count, kept, kept_fingerprints = rule
        page_limit = min(DEFAULT_PAGE_LIMIT if limit is None else limit, MAX_PAGE_LIMIT, max(max_results, 1))
        window, page = paged(range(len(kept)), None, offset, page_limit, lambda _i: ())
        dto: dict[str, Any] = {
            "scanId": scan.scan_id,
            "ruleId": rule_id,
            "violationCount": count,
            "retainedCount": len(kept),
            "truncated": len(kept) < count,
            "violations": [kept[i] for i in window],
        }
        if kept_fingerprints is not None:
            dto["fingerprints"] = [kept_fingerprints[i] for i in window]
        dto["page"] = page
        return dto
