"""Command-line and ini options for pytest --sharpit."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sharpit.engine.advisors.rules import SEVERITIES


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("sharpit")
    group.addoption(
        "--sharpit", action="store_true", default=None, dest="sharpit", help="capture test SQL and exceptions"
    )
    group.addoption("--sharpit-report", default=None, metavar="PATH", help="JSON report path")
    group.addoption("--sharpit-junit", default=None, metavar="PATH", help="JUnit findings path")
    group.addoption("--sharpit-sarif", default=None, metavar="PATH", help="SARIF 2.1.0 findings path")
    group.addoption(
        "--sharpit-max-queries", type=int, default=None, metavar="N", help="default call-phase query budget"
    )
    group.addoption("--sharpit-fail-on", default=None, metavar="SEV", help="advisor severity gate")
    group.addoption("--sharpit-allow-unknown", action="store_true", default=None, help="allow unknown capture status")
    group.addoption("--sharpit-app", default=None, metavar="MOD:ATTR", help="application to assess")
    group.addoption(
        "--sharpit-verbose", action="store_true", default=None, help="list advisor notes in the gate counts"
    )
    group.addoption(
        "--sharpit-require-app", action="store_true", default=None, help="no application found is unknown, not skipped"
    )
    group.addoption(
        "--sharpit-no-advisors",
        action="store_false",
        default=None,
        dest="sharpit_advisors",
        help="run count gates only",
    )
    group.addoption(
        "--sharpit-max-unattributed", type=float, default=None, metavar="PCT", help="unattributed SQL limit"
    )
    group.addoption(
        "--sharpit-report-only", action="store_true", default=None, help="report findings without gating pytest"
    )
    group.addoption("--sharpit-baseline", default=None, metavar="PATH", help="compare findings with a baseline file")
    group.addoption(
        "--sharpit-write-baseline",
        default=None,
        metavar="PATH",
        help="write a baseline after a complete run (the only way to write one)",
    )
    _add_ini(parser)


def _add_ini(parser: Any) -> None:
    parser.addini("sharpit", "Enable sharpit test capture", type="bool", default=False)
    parser.addini("sharpit_report", "Sharpit JSON report path", default="sharpit-report.json")
    parser.addini("sharpit_junit", "Sharpit JUnit report path", default="")
    parser.addini("sharpit_sarif", "Sharpit SARIF 2.1.0 report path", default="")
    # plain strings: ini type="int"/"float" are absent in pytest 8.2, and options.resolve converts them
    parser.addini("sharpit_max_queries", "Default sharpit per-test query budget", default="")
    parser.addini("sharpit_fail_on", "Minimum advisor severity that fails", default="HIGH")
    parser.addini("sharpit_allow_unknown", "Allow an unknown capture result", type="bool", default=False)
    parser.addini("sharpit_app", "Application module and attribute", default="")
    parser.addini("sharpit_verbose", "List advisor notes in the terminal gate counts", type="bool", default=False)
    parser.addini("sharpit_require_app", "Treat a run with no application as unknown", type="bool", default=False)
    parser.addini("sharpit_advisors", "Run application advisors", type="bool", default=True)
    parser.addini("sharpit_max_unattributed", "Maximum unattributed SQL percentage", default="10")
    parser.addini("sharpit_report_only", "Report findings without gating pytest", type="bool", default=False)
    parser.addini("sharpit_baseline", "Baseline file to compare", default="")


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
    require_app: bool = False
    verbose: bool = False
    report_only: bool = False
    baseline: Path | None = None
    write_baseline: Path | None = None
    sarif: Path | None = None


def _value(config: Any, option: Any, name: str, default: Any) -> Any:
    selected = getattr(option, f"sharpit_{name}", None)
    key = "sharpit" if name == "enabled" else f"sharpit_{name}"
    if name == "enabled":
        selected = getattr(option, "sharpit", None)
    try:
        configured = config.getini(key)
    except (ValueError, KeyError):
        configured = default
    return configured if selected is None else selected


def resolve(config: Any) -> PluginOptions:
    from sharpit.pytest_plugin.session import register_worker_apps  # lazy: keeps options import-light

    # the facade's pytest_configure resolves first on every process, the xdist controller included
    register_worker_apps(config)
    option = getattr(config, "known_args_namespace", config.option)

    fail_on = str(_value(config, option, "fail_on", "HIGH")).upper()
    if fail_on not in SEVERITIES:
        raise ValueError(f"--sharpit-fail-on must be one of {', '.join(SEVERITIES)}")
    maximum = _value(config, option, "max_queries", None)
    if maximum == "":  # the ini option unset
        maximum = None
    if maximum is not None and int(maximum) < 0:
        raise ValueError("--sharpit-max-queries must be non-negative")
    unattributed = float(_value(config, option, "max_unattributed", 10))
    if not 0 <= unattributed <= 100:
        raise ValueError("--sharpit-max-unattributed must be between 0 and 100")
    junit = _value(config, option, "junit", None)
    sarif = _value(config, option, "sarif", None)
    return PluginOptions(
        bool(_value(config, option, "enabled", False)),
        Path(_value(config, option, "report", "sharpit-report.json")),
        Path(junit) if junit else None,
        None if maximum is None else int(maximum),
        fail_on,
        bool(_value(config, option, "allow_unknown", False)),
        _value(config, option, "app", None),
        bool(_value(config, option, "advisors", True)),
        unattributed,
        bool(_value(config, option, "require_app", False)),
        bool(_value(config, option, "verbose", False))
        or (getattr(option, "verbose", 0) or 0) >= 2,  # -vv lists notes too
        bool(_value(config, option, "report_only", False)),
        Path(_value(config, option, "baseline", "")) if _value(config, option, "baseline", "") else None,
        Path(option.sharpit_write_baseline) if getattr(option, "sharpit_write_baseline", None) else None,
        Path(sarif) if sarif else None,
    )
