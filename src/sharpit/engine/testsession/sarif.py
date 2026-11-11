"""The SARIF 2.1.0 writer (``--sharpit-sarif``): wrong-value stub for the red commit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sharpit.engine.masking import Masker

FINGERPRINT_KEY = "stub"


def artifact_uri(path: str) -> str:
    return path


def to_sarif(data: dict[str, Any], masker: Masker) -> dict[str, Any]:
    del masker
    results = [
        {"ruleId": "", "level": "", "message": {"text": f["message"]}, "partialFingerprints": {}, "locations": [{}]}
        for f in data["findings"]
    ]
    return {"version": "", "runs": [{"tool": {"driver": {"name": "", "version": "", "rules": []}}, "results": results}]}


def write_sarif(path: Path, data: dict[str, Any], masker: Masker) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"stub": data}), encoding="utf-8")
