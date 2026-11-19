"""A baseline and a SARIF fingerprint for a swallowed exception survive a line moving above the handler (#66).

Each run is its own process: the engine caches a module's parsed source for the life of the process (a session never
edits the code it tests), so two in-process runs around an edit would read the first run's source."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE = Path(__file__).parents[1] / "fixtures" / "apps" / "swallowed_exception"
RULE = "sharpit.swallowed-exception"
ARGS = ("--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q")


def _sarif_fingerprints(path: Path) -> list[str]:
    results = json.loads(path.read_text("utf-8"))["runs"][0]["results"]
    return sorted(r["partialFingerprints"]["sharpitFingerprint/v1"] for r in results if r["ruleId"] == RULE)


def test_the_baseline_and_the_sarif_fingerprint_survive_a_moved_line(pytester: pytest.Pytester) -> None:
    weekapp = pytester.path / "weekapp.py"
    pytester.makepyfile(
        weekapp=(FIXTURE / "weekapp.py").read_text("utf-8"), test_weeks=(FIXTURE / "cases.py").read_text("utf-8")
    )
    pytester.runpytest_subprocess(
        *ARGS, "--sharpit-report-only", "--sharpit-write-baseline=baseline.json", "--sharpit-sarif=before.sarif"
    )
    weekapp.write_text("# a line added above every handler\n" + weekapp.read_text("utf-8"), encoding="utf-8")

    result = pytester.runpytest_subprocess(*ARGS, "--sharpit-baseline=baseline.json", "--sharpit-sarif=after.sarif")

    report: dict[str, Any] = json.loads((pytester.path / "report.json").read_text("utf-8"))
    planted = next((f for f in report["findings"] if f["ruleId"] == RULE), None)
    assert planted is not None, f"the second run reported no swallowed exception: {result.stdout.str()}"
    assert planted["baselineState"] == "existing", result.stdout.str()
    assert result.ret == 0, result.stdout.str()
    before = _sarif_fingerprints(pytester.path / "before.sarif")
    assert before, "the first run wrote no swallowed-exception result"
    assert _sarif_fingerprints(pytester.path / "after.sarif") == before
