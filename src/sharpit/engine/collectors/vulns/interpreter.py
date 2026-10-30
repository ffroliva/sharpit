"""Turns one OSV advisory into a finding for one installed package (port of BootUI ``OsvAdvisoryInterpreter`` plus the
advisory projection of ``OsvVulnerabilityScanner``: ``interpret``, ``vulnerability``, ``references``, withdrawal).

The query stays the detection authority: a contradictory or unsupported detail document still yields its finding, with
``unresolved`` set. Interpretation only selects the supported severity and verified upgrade candidates; it never
declares the installed version safe.

PyPI adaptations: ``affected[].package.ecosystem`` must be exactly ``"PyPI"`` and ``package.name`` matches when it is
the literal ``"*"`` or PEP 503-equal to the package name (OSV PyPI records use ``Django``, ``Jinja2``...). ``ECOSYSTEM``
range versions are ordered with ``packaging.version``; a version that is not valid PEP 440 is treated the way BootUI
treats a blank one (the range or installed version cannot be evaluated), because Maven's comparator orders any string
while PEP 440 does not. ``introduced: "0"`` still precedes every version, including ``0.dev0``.

Dropped: ``OsvAdvisoryInterpreterTests.neutralRecordsSnapshotMutableAdapterCollections`` (JVM-only: BootUI's adapter
records copy mutable Java lists; ``interpret`` reads the advisory dict once and keeps no reference to it).
"""

from __future__ import annotations

import functools
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast

from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from sharpit.engine.collectors.vulns.cvss import parse_score, severity_for, severity_from_text
from sharpit.engine.collectors.vulns.inventory import Package

ECOSYSTEM = "PyPI"
_EVENT_TYPES = ("introduced", "fixed", "last_affected", "limit")
_REFERENCE_PRIORITY = ("ADVISORY", "FIX")
_MAX_ALIASES = 20
_MAX_REFERENCES = 20
_MAX_FIXED_VERSIONS = 10


@dataclass
class Finding:
    """Contract 8 ``DependencyVulnerabilityDto``; ``unresolved`` is scan bookkeeping, not part of the DTO."""

    id: str
    summary: str | None
    details: str | None
    severity: str
    score: float | None
    aliases: list[str]
    references: list[str]
    fixed_versions: list[str]
    fix_available: bool
    epss_score: float | None = None
    epss_percentile: float | None = None
    dismissed: bool = False
    unresolved: bool = field(default=False, kw_only=True)

    def to_dto(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "summary": self.summary,
            "details": self.details,
            "severity": self.severity,
            "score": self.score,
            "aliases": list(self.aliases),
            "references": list(self.references),
            "fixedVersions": list(self.fixed_versions),
            "fixAvailable": self.fix_available,
            "epssScore": self.epss_score,
            "epssPercentile": self.epss_percentile,
            "dismissed": self.dismissed,
        }


def interpret(advisory: Any, pkg: Package, requested_id: str) -> Finding | None:
    """The finding for ``pkg``, or None when the document is not ``requested_id`` (a failed fetch) or is withdrawn."""
    if not isinstance(advisory, dict):
        return None
    doc = cast(dict[str, Any], advisory)
    vuln_id = _text(doc, "id")
    if vuln_id != requested_id or _text(doc, "withdrawn") is not None:
        return None
    severity, score, fixed, unresolved = _evaluate(doc, pkg)
    return Finding(
        id=requested_id,
        summary=_text(doc, "summary"),
        details=_text(doc, "details"),
        severity=severity,
        score=score,
        aliases=_strings(doc.get("aliases"))[:_MAX_ALIASES],
        references=_references(doc.get("references")),
        fixed_versions=fixed,
        fix_available=fix_available(pkg.version, fixed),
        unresolved=unresolved,
    )


def fix_available(current: str, fixed_versions: Iterable[str]) -> bool:
    """True only when some fixed version is positively comparable with, and newer than, ``current``."""
    installed = _version(current)
    if installed is None:
        return False
    return any((v := _version(candidate)) is not None and installed < v for candidate in fixed_versions)


# --- evidence projection (BootUI OsvVulnerabilityScanner.interpret/evidenceArray/event/severityEvidence) ---


@dataclass(frozen=True)
class _Severity:
    kind: str | None
    score: str | None


@dataclass(frozen=True)
class _Affected:
    ecosystem: str | None
    name: str | None
    versions: list[str | None]
    ranges: list[tuple[str | None, list[tuple[str, str] | None]] | None]
    severity: list[_Severity | None]


def _evidence(node: dict[str, Any], key: str) -> list[Any]:
    """Missing -> [], present but not a list (null included) -> [None]: malformed evidence is kept, never absent."""
    if key not in node:
        return []
    value = node[key]
    return cast(list[Any], value) if isinstance(value, list) else [None]


def _affected_list(doc: dict[str, Any]) -> list[_Affected | None]:
    result: list[_Affected | None] = []
    for item in _evidence(doc, "affected"):
        if not isinstance(item, dict):
            result.append(None)
            continue
        entry = cast(dict[str, Any], item)
        package = entry.get("package")
        pkg = cast(dict[str, Any], package) if isinstance(package, dict) else {}
        versions = [v if isinstance(v, str) else None for v in _evidence(entry, "versions")]
        ranges: list[tuple[str | None, list[tuple[str, str] | None]] | None] = []
        for raw in _evidence(entry, "ranges"):
            if isinstance(raw, dict):
                rng = cast(dict[str, Any], raw)
                ranges.append((_text(rng, "type"), [_event(e) for e in _evidence(rng, "events")]))
            else:
                ranges.append(None)
        result.append(_Affected(_text(pkg, "ecosystem"), _text(pkg, "name"), versions, ranges, _severities(entry)))
    return result


def _event(node: Any) -> tuple[str, str] | None:
    if isinstance(node, dict) and len(cast(dict[str, Any], node)) == 1:
        for kind in _EVENT_TYPES:
            version = _text(cast(dict[str, Any], node), kind)
            if version is not None:
                return kind, version
    return None  # BootUI's Event(null, null)


def _severities(node: dict[str, Any]) -> list[_Severity | None]:
    result: list[_Severity | None] = []
    for item in _evidence(node, "severity"):
        entry = cast(dict[str, Any], item) if isinstance(item, dict) else {}
        result.append(_Severity(_text(entry, "type"), _text(entry, "score")) if item is not None else None)
    return result


# --- interpretation (BootUI OsvAdvisoryInterpreter.interpret) ---


class _Applicability(Enum):
    MATCHED = 1
    NOT_MATCHED = 2
    UNRESOLVED = 3


@dataclass(frozen=True)
class _Event:
    kind: str
    raw: str
    version: Version
    beginning: bool  # introduced "0": precedes every version


class _Timeline:
    def __init__(self, rng: tuple[str | None, list[tuple[str, str] | None]] | None) -> None:
        self.events: list[_Event] = []
        self.limits: list[Version | None] = []  # None is the "*" limit
        self.valid = False
        if rng is None or rng[0] != "ECOSYSTEM" or not rng[1]:
            return
        kinds: set[str] = set()
        for event in rng[1]:
            if event is None:
                return
            kind, raw = event
            if kind == "limit" and raw == "*":
                self.limits.append(None)
                continue
            version = _version(raw)
            if version is None:
                return
            kinds.add(kind)
            if kind == "limit":
                self.limits.append(version)
            else:
                self.events.append(_Event(kind, raw, version, kind == "introduced" and raw == "0"))
        if "introduced" not in kinds or {"fixed", "last_affected"} <= kinds:
            return
        self.events.sort(key=functools.cmp_to_key(_compare_events))
        for previous, current in zip(self.events, self.events[1:], strict=False):
            if (
                previous.kind != current.kind
                and not (previous.kind == "introduced" and current.kind == "last_affected")
                and previous.beginning == current.beginning
                and previous.version == current.version
            ):
                return  # contradictory status changes at one equivalent boundary have no unique order
        self.valid = True

    def evaluate(self, raw: str) -> _Applicability:
        version = _version(raw)
        if not self.valid or version is None:
            return _Applicability.UNRESOLVED
        if self.limits and not any(limit is None or version < limit for limit in self.limits):
            return _Applicability.NOT_MATCHED
        affected = False
        for event in self.events:
            compared = 1 if event.beginning else _cmp(version, event.version)
            if event.kind == "introduced" and compared >= 0:
                affected = True
            elif (event.kind == "fixed" and compared >= 0) or (event.kind == "last_affected" and compared > 0):
                affected = False
        return _Applicability.MATCHED if affected else _Applicability.NOT_MATCHED

    def closing_fix(self, raw: str) -> str | None:
        if self.evaluate(raw) is not _Applicability.MATCHED:
            return None
        version = _version(raw)
        for event in self.events:
            if event.kind == "fixed" and version is not None and version < event.version:
                return event.raw
        return None


def _compare_events(left: _Event, right: _Event) -> int:
    if left.beginning != right.beginning:
        return -1 if left.beginning else 1
    compared = _cmp(left.version, right.version)
    if compared == 0:
        # inclusive singleton intervals close after their equal introduction, in either input order
        return (left.kind == "last_affected") - (right.kind == "last_affected")
    return compared


class _Entry:
    def __init__(self, affected: _Affected) -> None:
        self.affected = affected
        self.timelines = [_Timeline(r) for r in affected.ranges]

    def evaluate(self, version: str) -> tuple[_Applicability, bool]:
        if not version.strip():
            return _Applicability.UNRESOLVED, True
        matched = False
        unresolved = not self.affected.versions and not self.timelines
        for listed in self.affected.versions:
            if listed is None or not listed.strip():
                unresolved = True
            elif version == listed:
                matched = True
        for timeline in self.timelines:
            applicability = timeline.evaluate(version)
            matched |= applicability is _Applicability.MATCHED
            unresolved |= applicability is _Applicability.UNRESOLVED
        if matched:
            return _Applicability.MATCHED, unresolved
        return (_Applicability.UNRESOLVED if unresolved else _Applicability.NOT_MATCHED), unresolved


def _evaluate(doc: dict[str, Any], pkg: Package) -> tuple[str, float | None, list[str], bool]:
    matching: list[_Entry] = []
    unknown_identity = False
    for item in _affected_list(doc):
        if item is None or item.ecosystem is None or item.name is None:
            unknown_identity = True
        elif (
            pkg.name.strip()
            and item.ecosystem == ECOSYSTEM
            and (item.name == "*" or canonicalize_name(item.name) == pkg.name)
        ):
            matching.append(_Entry(item))

    applicable = False
    unresolved = unknown_identity
    package_severity_supplied = False
    score: float | None = None
    candidates: list[str] = []
    for entry in matching:
        applicability, entry_unresolved = entry.evaluate(pkg.version)
        unresolved |= entry_unresolved
        if applicability is _Applicability.MATCHED:
            applicable = True
            package_severity_supplied |= bool(entry.affected.severity)
            score = _maximum(score, _highest_score(entry.affected.severity))
            candidates += [fix for t in entry.timelines if (fix := t.closing_fix(pkg.version)) is not None]
    unresolved |= not applicable
    if not package_severity_supplied:
        score = _highest_score(_severities(doc))

    verified: list[str] = []
    for candidate in candidates:
        if not fix_available(pkg.version, [candidate]):
            continue
        unaffected = bool(matching) and all(
            entry.evaluate(candidate)[0] is _Applicability.NOT_MATCHED for entry in matching
        )
        # missing package identity might describe the proposed target; it cannot verify an upgrade
        if unaffected and not unknown_identity:
            verified.append(candidate)
    severity = severity_from_text(_database_severity(doc)) if score is None else severity_for(score)
    return severity, score, _order_fixed_versions(verified), unresolved


def _database_severity(doc: dict[str, Any]) -> str | None:
    specific = doc.get("database_specific")
    return _text(cast(dict[str, Any], specific), "severity") if isinstance(specific, dict) else None


def _highest_score(severity: list[_Severity | None]) -> float | None:
    score: float | None = None
    for assessment in severity:
        if assessment is not None:
            score = _maximum(score, parse_score(assessment.kind, assessment.score))
    return score


def _maximum(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    return left if right is None else max(left, right)


def _order_fixed_versions(versions: list[str]) -> list[str]:
    """Distinct, trimmed, ordered by PEP 440 then case-insensitive text (BootUI ``orderFixedVersions``), max 10."""
    distinct = list(dict.fromkeys(v.strip() for v in versions if v.strip()))
    return sorted(distinct, key=functools.cmp_to_key(compare_versions))[:_MAX_FIXED_VERSIONS]


def compare_versions(left: str, right: str) -> int:
    lv, rv = _version(left), _version(right)
    if lv is not None and rv is not None and lv != rv:
        return _cmp(lv, rv)
    return _cmp((left.lower(), left), (right.lower(), right))


# --- advisory projection helpers ---


def _references(node: Any) -> list[str]:
    if not isinstance(node, list):
        return []
    items = [cast(dict[str, Any], r) if isinstance(r, dict) else {} for r in cast(list[Any], node)]
    ordered = sorted(items, key=lambda r: _reference_rank(_text(r, "type")))  # stable: OSV order within a rank
    urls = [url for r in ordered if (url := _text(r, "url")) is not None]
    return list(dict.fromkeys(urls))[:_MAX_REFERENCES]


def _reference_rank(kind: str | None) -> int:
    return _REFERENCE_PRIORITY.index(kind) if kind in _REFERENCE_PRIORITY else len(_REFERENCE_PRIORITY)


def _strings(node: Any) -> list[str]:
    if not isinstance(node, list):
        return []
    return list(dict.fromkeys(v for v in cast(list[Any], node) if isinstance(v, str) and v.strip()))


def _text(node: dict[str, Any], key: str) -> str | None:
    """BootUI ``text``: a non-blank string field, else None."""
    value = node.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _version(raw: str | None) -> Version | None:
    if raw is None or not raw.strip():
        return None
    try:
        return Version(raw)
    except InvalidVersion:
        return None


def _cmp(left: Any, right: Any) -> int:
    return (left > right) - (left < right)
