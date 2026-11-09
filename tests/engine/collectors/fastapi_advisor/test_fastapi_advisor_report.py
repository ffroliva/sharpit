"""The fastapi advisor report against the BootUI 2.2.0 ``spring`` goldens (WAVE-B §1, §7; spec §5 post-scan parity)."""

from __future__ import annotations

from pathlib import Path

import pytest

from golden import ROOT, assert_enum_values, assert_parity
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.findings import Finding
from sharpit.engine.advisors.report import evidence
from sharpit.engine.advisors.scan import Evaluation
from sharpit.engine.collectors.fastapi_advisor.report import RULES, FastapiAdvisor
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.singleflight import SingleFlight

MASKER = Masker(Exposure.MASKED, True)


def _advisor(tmp_path: Path, done: Evaluation | None = None) -> FastapiAdvisor:
    evaluation = done or Evaluation("SCANNED", "done", (), (), evidence(True, True, []), {})
    return FastapiAdvisor(
        lambda _request: evaluation, DismissalStore(tmp_path), MASKER, SingleFlight(), max_retained=10000
    )


def test_report_golden_parity(tmp_path: Path) -> None:
    # ported: SpringScannerTests.initialReportIsNotScanned
    report = _advisor(tmp_path).report()
    assert report["scan"]["status"] == "NOT_SCANNED"
    assert_parity("fastapi", "captured", report)
    assert_enum_values("fastapi", "captured", report)


def _scanned(tmp_path: Path) -> FastapiAdvisor:
    rule = RULES[0]
    finding = Finding(rule.id, "fastapi", rule.severity, "app.main:handler", "GET /a (app.main:handler): line 3")
    done = Evaluation(
        "SCANNED",
        "FastAPI Advisor completed against 1 route handler(s).",
        tuple(r.id for r in RULES),
        (finding,),
        evidence(True, True, []),
        {"inspected": ["Routes: 1; source parsed, never executed."], "components": 1},
    )
    return _advisor(tmp_path, done)


def test_post_scan_golden_parity(tmp_path: Path) -> None:
    folder = ROOT / "fastapi"
    if not (folder / "scanned.captured.json").is_file() or not (folder / "violations.captured.json").is_file():
        pytest.skip("post-scan golden absent")
    advisor = _scanned(tmp_path)
    scanned = advisor.scan()
    assert_parity("fastapi", "scanned.captured", scanned)
    assert_enum_values("fastapi", "scanned.captured", scanned)
    page = advisor.violations(RULES[0].id, scanned["violationDetails"]["scanId"], 0, 10)
    assert_parity("fastapi", "violations.captured", page)
