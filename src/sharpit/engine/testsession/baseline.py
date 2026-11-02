"""Stable, explicit baseline file format for pytest gate findings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sharpit.engine.advisors.findings import Finding

SCHEMA = "sharpit-baseline/1"


@dataclass(frozen=True)
class Entry:
    fingerprint: str
    rule_id: str
    target: str
    message: str
    observed: int | None


@dataclass(frozen=True)
class Baseline:
    entries: dict[str, Entry]
    raw: bytes


@dataclass(frozen=True)
class Comparison:
    findings: tuple[Finding, ...]
    fixed: tuple[Entry, ...] | None
    fixed_reason: str | None


def read(path: Path) -> Baseline:
    """Placeholder returning an invalid baseline until the baseline loader is implemented."""
    del path
    return Baseline({}, b"{}")


def compare(findings: tuple[Finding, ...], baseline: Baseline | None, *, partial: bool) -> Comparison:
    """Placeholder comparison; implemented after the contract tests are committed."""
    del findings, baseline, partial
    return Comparison((), (), None)


def write(path: Path, findings: tuple[Finding, ...]) -> None:
    """Placeholder baseline writer."""
    del findings
    path.write_text("{}", encoding="utf-8")
