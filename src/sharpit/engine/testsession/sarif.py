"""The SARIF 2.1.0 writer (``--sharpit-sarif PATH``): one SARIF log read from the ``sharpit-report/1`` dict.

Every text goes through the report masker again, even though the sink masked it once: SARIF is uploaded to code
hosts, so a finding message is never trusted to be clean. A finding's file location, when it has one, becomes a
``%SRCROOT%``-relative POSIX URI; a path that is absolute, has a drive or scheme, or climbs out with ``..`` loses its
location and keeps the finding, and so does a path the masker changed. A finding without a file location carries
its target as a logical location.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from sharpit.engine.masking import Masker
from sharpit.engine.testsession.report import write_json

SCHEMA_URI = "https://json.schemastore.org/sarif-2.1.0.json"
FINGERPRINT_KEY = "sharpitFingerprint/v1"  # the location-free ``Finding.fingerprint``; bump the suffix if it changes
INFORMATION_URI = "https://github.com/ffroliva/sharpit"
SOURCE_ROOT = "%SRCROOT%"
_LEVELS = {"CRITICAL": "error", "HIGH": "error", "MEDIUM": "warning", "LOW": "note", "INFO": "note"}
_SCHEME_OR_DRIVE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def artifact_uri(path: str) -> str | None:
    """``path`` as a root-relative, percent-encoded POSIX URI, or None when it is empty or leaves the root."""
    posix = path.replace("\\", "/")
    if not posix or posix.startswith("/") or _SCHEME_OR_DRIVE.match(posix):
        return None
    parts = [part for part in posix.split("/") if part not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return quote("/".join(parts), safe="/")


def _text(masker: Masker, text: object) -> str:
    return masker.mask_text(str(text)) or ""


def _location(finding: Mapping[str, Any], masker: Masker) -> dict[str, Any]:
    location: dict[str, Any] = {}
    place = finding.get("location")
    if isinstance(place, Mapping):
        place = cast("Mapping[str, Any]", place)
        path = place.get("path")
        # a path masking changed names no real file: drop it rather than point at one that does not exist
        uri = artifact_uri(path) if isinstance(path, str) and _text(masker, path) == path else None
        if uri is not None:
            physical: dict[str, Any] = {"artifactLocation": {"uri": uri, "uriBaseId": SOURCE_ROOT}}
            line = place.get("line")
            if isinstance(line, int) and not isinstance(line, bool) and line >= 1:
                physical["region"] = {"startLine": line}
            location["physicalLocation"] = physical
    location["logicalLocations"] = [{"fullyQualifiedName": _text(masker, finding["target"])}]
    return location


def _result(finding: Mapping[str, Any], masker: Masker) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ruleId": finding["ruleId"],
        "level": _LEVELS[finding["severity"]],
        "message": {"text": _text(masker, finding["message"])},
        "locations": [_location(finding, masker)],
        "partialFingerprints": {FINGERPRINT_KEY: finding["fingerprint"]},
        "properties": {
            "advisor": finding["advisor"],
            "severity": finding["severity"],
            "testNodeId": None if finding.get("testNodeId") is None else _text(masker, finding["testNodeId"]),
        },
    }
    if finding.get("dismissed"):
        result["suppressions"] = [{"kind": "external", "justification": "dismissed in sharpit"}]
    elif finding.get("baselineState") == "existing":
        result["suppressions"] = [{"kind": "external", "justification": "accepted in the sharpit baseline"}]
    return result


def to_sarif(data: Mapping[str, Any], masker: Masker) -> dict[str, Any]:
    """One run: ``tool.driver`` names sharpit and each rule once; one result per finding, in report order."""
    findings: list[Mapping[str, Any]] = data["findings"]
    rules = sorted({finding["ruleId"] for finding in findings})
    driver = {
        "name": "sharpit",
        "version": data["tool"]["version"],
        "informationUri": INFORMATION_URI,
        "rules": [{"id": rule} for rule in rules],
    }
    return {
        "$schema": SCHEMA_URI,
        "version": "2.1.0",
        "runs": [{"tool": {"driver": driver}, "results": [_result(finding, masker) for finding in findings]}],
    }


def write_sarif(path: Path, data: Mapping[str, Any], masker: Masker) -> None:
    """UTF-8, atomic, like the JSON report (the xdist controller alone calls it, from ``write_report``)."""
    write_json(path, to_sarif(data, masker))
