"""Command-line and ini options for pytest --sharpit."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sharpit.engine.advisors.rules import SEVERITIES


@dataclass(frozen=True)
class PluginOptions:
    enabled: bool
    report: Path
    junit: Path | None
    max_queries: int | None
    fail_on: str
    allow_unknown: bool
    app: str | None
    advisors: bool
    max_unattributed: float


def resolve(config: Any) -> PluginOptions:
    option = getattr(config, "known_args_namespace", config.option)

    def value(name: str, default: Any) -> Any:
        selected = getattr(option, f"sharpit_{name}", None)
        key = "sharpit" if name == "enabled" else f"sharpit_{name}"
        if name == "enabled":
            selected = getattr(option, "sharpit", None)
        try:
            configured = config.getini(key)
        except (ValueError, KeyError):
            configured = default
        return configured if selected is None else selected

    fail_on = str(value("fail_on", "HIGH")).upper()
    if fail_on not in SEVERITIES:
        raise ValueError(f"--sharpit-fail-on must be one of {', '.join(SEVERITIES)}")
    maximum = value("max_queries", None)
    if maximum == "":  # the ini option unset
        maximum = None
    if maximum is not None and int(maximum) < 0:
        raise ValueError("--sharpit-max-queries must be non-negative")
    unattributed = float(value("max_unattributed", 10))
    if not 0 <= unattributed <= 100:
        raise ValueError("--sharpit-max-unattributed must be between 0 and 100")
    junit = value("junit", None)
    return PluginOptions(
        bool(value("enabled", False)),
        Path(value("report", "sharpit-report.json")),
        Path(junit) if junit else None,
        None if maximum is None else int(maximum),
        fail_on,
        bool(value("allow_unknown", False)),
        value("app", None),
        bool(value("advisors", True)),
        unattributed,
    )
