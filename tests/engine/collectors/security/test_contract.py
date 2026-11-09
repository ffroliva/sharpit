"""The security advisor report against BootUI 2.2.0's ``SecurityReport`` (WAVE-B contract §1, §2)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.middleware.cors import CORSMiddleware

from fastapi import FastAPI
from golden import ROOT, assert_enum_values, assert_parity
from sharpit.engine.collectors.security import Inputs
from sharpit.engine.collectors.security.report import SecurityService

ServiceFor = Callable[[Callable[[], Inputs]], SecurityService]
InputsOf = Callable[..., Inputs]


def _violating_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)
    app.post("/items")(lambda: "created")
    return app


def test_report_golden_parity(service_for: ServiceFor, inputs_of: InputsOf):
    # ported: SecurityScannerTests.initialReportDoesNotInspectConfigurationBeforeExplicitScan
    service = service_for(lambda: inputs_of(_violating_app()))
    report = service.report()
    assert_parity("security", "report", report)
    assert_enum_values("security", "report", report)


def test_post_scan_golden_parity(service_for: ServiceFor, inputs_of: InputsOf):
    folder: Path = ROOT / "security"
    if not (folder / "scanned.captured.json").is_file():
        pytest.skip("post-scan golden absent (G0)")
    service = service_for(lambda: inputs_of(_violating_app()))
    scanned = service.scan()
    assert_parity("security", "scanned", scanned)
    assert_enum_values("security", "scanned", scanned)
    rule_id = scanned["results"][0]["id"]
    page = service.violations(rule_id, scanned["violationDetails"]["scanId"], 0, 100)
    assert_parity("security", "violations", page)
