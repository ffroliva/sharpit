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
