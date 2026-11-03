"""One security scan on the shared advisor core: statuses, messages, evidence, analysis errors and its inputs."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.middleware.cors import CORSMiddleware
from starlette.applications import Starlette

from fastapi import FastAPI
from sharpit.engine import appsource
from sharpit.engine.collectors.security import Inputs, Violation, report
from sharpit.engine.collectors.security.report import SecurityService, build_inputs, view_of
from sharpit.fastapi.introspector import FastApiIntrospector
from sharpit.settings import load_settings

ServiceFor = Callable[[Callable[[], Inputs]], SecurityService]
InputsOf = Callable[..., Inputs]
SOURCE_RULES = 5  # SEC-AUTH-001/002/006, SEC-CONFIG-007, SEC-SRC-001
FRAMEWORK_LOGGERS = ("fastapi", "starlette", "uvicorn", "sqlalchemy.engine")
PARTIAL_TAIL = " Unsupported or incomplete evidence remains unknown; skipped checks are not security passes."


def _violating_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)
    app.post("/items")(lambda: "created")
    return app


def test_scan_disabled_when_the_app_is_not_fastapi(service_for: ServiceFor, inputs_of: InputsOf):
    # ported: SecurityScannerTests.scanReturnsStableDisabledReportWhenNoFilterChainProxyIsAvailable
    scanned = service_for(lambda: inputs_of(Starlette())).scan()
    scan = scanned["scan"]
    assert (scan["status"], scan["message"], scan["rulesEvaluated"]) == (
        "DISABLED",
        "No FastAPI application was found to inspect.",
        0,
    )


def test_scan_message_counts_middleware_stacks(service_for: ServiceFor, inputs_of: InputsOf, tmp_path: Path):
    (tmp_path / "app.py").write_text("", encoding="utf-8")
    scanned = service_for(lambda: inputs_of(_violating_app(), tmp_path / "app.py")).scan()
    scan = scanned["scan"]
    assert (scan["status"], scan["message"]) == ("SCANNED", "Security Advisor completed against 1 middleware stack.")


def test_scan_reports_violating_rules(service_for: ServiceFor, inputs_of: InputsOf, tmp_path: Path):
    # ported: SecurityScannerTests.everyActiveRuleRoutesThroughTheFailClosedBase (every rule is evaluated)
    (tmp_path / "app.py").write_text("", encoding="utf-8")
    scanned = service_for(lambda: inputs_of(_violating_app(), tmp_path / "app.py")).scan()
    ids = [r["id"] for r in scanned["results"]]
    assert ids == ["SEC-AUTHZ-002", "SEC-CORS-002", "SEC-FAPI-001"]
    assert scanned["rulesEvaluated"] == len(report.RULES)


def test_missing_inventory_makes_scan_partial(service_for: ServiceFor, inputs_of: InputsOf, tmp_path: Path):
    # ported: SecurityScannerTests.missingRequiredOperationInventoryMakesScanStatusAndEvidencePartial
    (tmp_path / "app.py").write_text("", encoding="utf-8")
    app = _violating_app()

    async def legacy(scope: Any, receive: Any, send: Any) -> None:
        raise AssertionError("a mounted application was called")

    app.mount("/legacy", legacy)
    scanned = service_for(lambda: inputs_of(app, tmp_path / "app.py")).scan()
    assert (scanned["scan"]["status"], scanned["evidence"]["coverageComplete"]) == ("PARTIAL", False)
    assert scanned["scan"]["message"].endswith(PARTIAL_TAIL)


def test_rule_errors_are_analysis_errors(service_for: ServiceFor, inputs_of: InputsOf, monkeypatch: pytest.MonkeyPatch):
    # ported: SecurityScannerTests.ruleEvaluationWrapsRuntimeExceptionAsErrorResult,
    # SecurityScannerTests.analysisErrorsKeepsOnlyErrorResultsSortedById
    def boom(_inputs: Inputs) -> list[Violation]:
        raise RuntimeError("rule failed")

    broken = {"SEC-CORS-002", "SEC-AUTH-007"}
    rules = tuple(replace(r, check=boom) if r.definition.id in broken else r for r in report.RULES)
    monkeypatch.setattr(report, "RULES", rules)
    scanned = service_for(lambda: inputs_of(_violating_app())).scan()
    errors = [(r["id"], r["status"]) for r in scanned["analysisErrors"]]
    assert errors == [("SEC-AUTH-007", "ERROR"), ("SEC-CORS-002", "ERROR")]
    assert "SEC-CORS-002" not in [r["id"] for r in scanned["results"]]
    assert scanned["scan"]["status"] == "PARTIAL"


def test_unreadable_source_is_a_limitation(service_for: ServiceFor, inputs_of: InputsOf):
    # ported: SecurityScannerTests.noApplicableTargetsAndUnavailableDiscoveryNeverCompleteChecks
    reason = "the application is defined in __main__ (a script run directly): not scanned; set app_package"
    scanned = service_for(lambda: replace(inputs_of(_violating_app()), limitations=(reason,))).scan()
    assert scanned["rulesEvaluated"] == len(report.RULES) - SOURCE_RULES
    assert scanned["evidence"]["limitations"] == [f"application source: {reason}"]
    assert scanned["scan"]["status"] == "PARTIAL"


def _shop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    package = tmp_path / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "settings.py").write_text('import os\nKEY = os.getenv("SECRET_KEY", "dev-secret-123")\n', "utf-8")
    module = ModuleType("shop")
    module.__file__ = str(package / "__init__.py")
    monkeypatch.setitem(sys.modules, "shop", module)
    return package


def test_scan_uses_the_one_package_root_resolver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _shop(tmp_path, monkeypatch)
    calls: list[tuple[object, str | None]] = []
    real = appsource.resolve_package_root

    def spy(app: object, modules: Any, **kwargs: Any) -> Path | None:
        calls.append((app, kwargs.get("app_package")))
        return real(app, modules, **kwargs)

    monkeypatch.setattr(appsource, "resolve_package_root", spy)
    app = _violating_app()
    introspector = FastApiIntrospector(app)
    settings = load_settings({"app_package": "shop"}, {})
    inputs = build_inputs(introspector.security_model(), introspector.security_facts(), app, settings, {})
    assert calls == [(app, "shop")]
    assert inputs.source is not None
    assert sorted(inputs.source.modules) == ["shop", "shop.settings"]


def test_view_reads_profiles_and_levels_without_creating_loggers():
    settings = load_settings({}, {})
    loggers = logging.Logger.manager.loggerDict
    absent = [name for name in FRAMEWORK_LOGGERS if name not in loggers]
    uvicorn = logging.getLogger("uvicorn")
    level = uvicorn.level
    uvicorn.setLevel(logging.DEBUG)
    try:
        production = view_of(settings, {"APP_ENV": "prod"})
        development = view_of(settings, {"APP_ENV": "dev"})
    finally:
        uvicorn.setLevel(level)
    assert (production.production, development.production) == (True, False)
    assert "uvicorn" in production.debug_loggers
    assert [name for name in absent if name in loggers] == []
