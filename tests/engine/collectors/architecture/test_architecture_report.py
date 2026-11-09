"""Tests for the architecture advisor report shape and golden parity (spec §5.5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.golden import assert_enum_values, assert_parity

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.collectors.architecture.report import ArchitectureService
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.singleflight import SingleFlight


def test_report_golden_parity(tmp_path: Path) -> None:
    # ported: ArchitectureScannerTests.initialReportIsNotScanned
    service = ArchitectureService(
        base_packages=lambda: ["com.ffroliva.tinyledger"],
        dismissals=DismissalStore(tmp_path),
        masker=Masker(Exposure.MASKED, True),
        single_flight=SingleFlight(),
        max_retained=1000,
    )
    report = service.report()
    assert_parity("architecture", "captured", report)
    assert_enum_values("architecture", "captured", report)


def test_post_scan_golden_parity(tmp_path: Path) -> None:
    # ported: ArchitectureScannerTests.scanRefreshesCachedReportAndAppliesDismissals
    path = Path("tests/fixtures/bootui/2.2.0/architecture/scanned.captured.json")
    if not path.is_file():
        pytest.skip("post-scan golden absent")
    service = ArchitectureService(
        base_packages=lambda: ["com.ffroliva.tinyledger"],
        dismissals=DismissalStore(tmp_path),
        masker=Masker(Exposure.MASKED, True),
        single_flight=SingleFlight(),
        max_retained=1000,
    )
    report = service.scan()
    assert_parity("architecture", "scanned.captured", report)
    assert_enum_values("architecture", "scanned.captured", report)


def test_post_scan_golden_parity_on_fixture_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: ArchitectureScannerTests.scanRefreshesCachedReportAndAppliesDismissals (review fix 8: a real scan)
    import sys  # noqa: PLC0415
    import types  # noqa: PLC0415

    from sharpit.engine.collectors.architecture.report import scan_application  # noqa: PLC0415

    pkg = tmp_path / "arch_golden_app"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "a.py").write_text("import arch_golden_app.b\n", encoding="utf-8")
    (pkg / "b.py").write_text("import arch_golden_app.a\n", encoding="utf-8")
    module = types.ModuleType("arch_golden_app")
    module.__file__ = str(pkg / "__init__.py")
    module.__path__ = [str(pkg)]
    monkeypatch.setitem(sys.modules, "arch_golden_app", module)
    service = ArchitectureService(
        base_packages=lambda: [],
        dismissals=DismissalStore(tmp_path / "state"),
        masker=Masker(Exposure.MASKED, True),
        single_flight=SingleFlight(),
        max_retained=1000,
        run_scan=lambda _request: scan_application(None, "arch_golden_app"),
    )

    report = service.scan()
    violated = [r for r in report["results"] if r["violationCount"]]
    assert report["scan"]["status"] == "SCANNED"
    assert "ARCH-PKG-001" in [r["id"] for r in violated]
    page = service.violations("ARCH-PKG-001", report["violationDetails"]["scanId"], 0, 100, 1000)
    assert page["page"]["total"] == 1

    goldens = Path(__file__).resolve().parents[3] / "fixtures" / "bootui" / "2.2.0" / "architecture"
    if (goldens / "scanned.captured.json").is_file():
        assert_parity("architecture", "scanned.captured", report)
        assert_enum_values("architecture", "scanned.captured", report)
    if (goldens / "violations.captured.json").is_file():
        assert_parity("architecture", "violations.captured", page)
    if not ((goldens / "scanned.captured.json").is_file() and (goldens / "violations.captured.json").is_file()):
        pytest.skip("post-scan golden absent")


def test_report_speaks_sharpit_not_bootui(tmp_path: Path) -> None:
    service = ArchitectureService(
        base_packages=lambda: ["pkg"],
        dismissals=DismissalStore(tmp_path),
        masker=Masker(Exposure.MASKED, True),
        single_flight=SingleFlight(),
        max_retained=1000,
    )
    scan = service.report()["scan"]
    assert scan["analyzer"] == "sharpit architecture hygiene"
    assert "bootui" not in scan["message"].lower()
    assert "sharpit architecture scan" in scan["message"]
