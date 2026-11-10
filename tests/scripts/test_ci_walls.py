"""Tests for scripts/ci/ci_walls.py (W0b Task 1).

Verifies the attempt-1 critical path table reproduction from W0b-step0.md §2.1,
noise measurement, and the noise gain rule (after-max < before-min).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from _load import load_script

ci_walls = load_script("scripts/ci/ci_walls.py")

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ci_walls"
REQUIRED = ci_walls.DEFAULT_REQUIRED


def test_walls_match_the_step0_table_for_three_runs() -> None:
    expected_table = [
        ("42742037589", 310.0, 648.0),
        ("42738503931", 320.0, 673.0),
        ("42721024336", 413.0, 626.0),
    ]
    for run_id, expected_a, expected_b in expected_table:
        fixture = json.loads((FIXTURES / f"{run_id}.json").read_text(encoding="utf-8"))
        w = ci_walls.walls(fixture["run"], fixture["jobs"], REQUIRED)
        assert w.a == expected_a
        assert w.b == expected_b


def test_walls_rejects_an_attempt_other_than_one() -> None:
    fixture = json.loads((FIXTURES / "42742037589.json").read_text(encoding="utf-8"))
    bad_run = dict(fixture["run"], run_attempt=2)
    with pytest.raises(ValueError, match="attempt 2"):
        ci_walls.walls(bad_run, fixture["jobs"], REQUIRED)


def test_walls_reports_the_event_of_the_run() -> None:
    fixture = json.loads((FIXTURES / "42742037589.json").read_text(encoding="utf-8"))
    w = ci_walls.walls(fixture["run"], fixture["jobs"], REQUIRED)
    assert w.event == fixture["run"]["event"]


def test_a_gain_counts_only_when_after_max_is_below_before_min() -> None:
    # Gain counts only when after-max < before-min
    assert ci_walls.gain([10.0, 11.0, 12.0], [8.0, 9.0, 9.5]) is True
    assert ci_walls.gain([10.0, 11.0, 12.0], [9.0, 10.0, 10.5]) is False
    assert ci_walls.gain([10.0, 11.0, 12.0], [9.0, 9.5, 10.0]) is False


def test_noise_reports_max_minus_min_duration_per_job() -> None:
    fixtures = [
        json.loads((FIXTURES / f"{rid}.json").read_text(encoding="utf-8"))
        for rid in ["42742037589", "42738503931", "42721024336"]
    ]
    wall_runs = [ci_walls.walls(f["run"], f["jobs"], REQUIRED) for f in fixtures]
    n = ci_walls.noise(wall_runs)
    assert n.get("masking gates (windows-latest)") == 156.0


def test_walls_computes_queue_breakdown_and_per_os_critical() -> None:
    fixture = json.loads((FIXTURES / "42742037589.json").read_text(encoding="utf-8"))
    w = ci_walls.walls(fixture["run"], fixture["jobs"], REQUIRED)
    assert w.max_queue == 644.0
    jt = w.per_job["masking gates (windows-latest)"]
    assert jt.queue == 85.0
    assert jt.setup == 22.0
    assert jt.test == 526.0
    assert jt.teardown == 7.0
    assert jt.duration == 555.0
    assert w.per_os_critical["windows"] == "masking gates (windows-latest)"
    assert w.per_os_critical["ubuntu"] == "masking-gates-check"


def test_required_job_not_success_makes_required_wall_undefined() -> None:
    run = {"created_at": "2026-11-10T00:00:00Z", "run_attempt": 1}
    jobs = [
        {
            "name": next(iter(REQUIRED)),
            "started_at": "2026-11-10T00:00:01Z",
            "completed_at": "2026-11-10T00:00:02Z",
            "conclusion": "failure",
        }
    ]

    assert ci_walls.walls(run, jobs).a is None


def test_required_none_uses_default_required_set() -> None:
    fixture = json.loads((FIXTURES / "42742037589.json").read_text(encoding="utf-8"))

    assert ci_walls.walls(fixture["run"], fixture["jobs"], None).a == 310.0


def test_protection_lookup_failure_warns_and_exits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_lookup(*args: str) -> object:
        raise ci_walls.subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(ci_walls, "_fetch_gh_json", fail_lookup)
    monkeypatch.setattr(sys, "argv", ["ci_walls.py", str(FIXTURES / "42742037589.json"), "--required-from-protection"])

    with pytest.raises(SystemExit) as exc:
        ci_walls.main()

    assert exc.value.code != 0
    assert "warning" in capsys.readouterr().err.lower()


def test_fixture_steps_are_scrubbed_and_have_only_safe_fields() -> None:
    allowed = {"name", "started_at", "completed_at", "conclusion"}
    for path in FIXTURES.glob("*.json"):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        assert "head_branch" not in fixture["run"]
        assert "head_sha" not in fixture["run"]
        for job in fixture["jobs"]:
            for step in job.get("steps", []):
                assert set(step) == allowed
                assert "/home/runner" not in json.dumps(step)
                assert "$RUNNER_TEMP" not in json.dumps(step)
                assert "if [[" not in step["name"]
                assert "uv run" not in step["name"]


@pytest.mark.parametrize(
    ("run_id", "ubuntu_timings", "windows_timings"),
    [
        ("42742037589", (304.0, 2.0, 0.0, 2.0), (85.0, 22.0, 526.0, 7.0)),
        ("42738503931", (247.0, 1.0, 0.0, 3.0), (27.0, 22.0, 611.0, 6.0)),
        ("42721024336", (281.0, 1.0, 0.0, 2.0), (137.0, 16.0, 462.0, 5.0)),
    ],
)
def test_per_job_timings_cover_each_os_for_each_run(
    run_id: str, ubuntu_timings: tuple[float, ...], windows_timings: tuple[float, ...]
) -> None:
    fixture = json.loads((FIXTURES / f"{run_id}.json").read_text(encoding="utf-8"))
    w = ci_walls.walls(fixture["run"], fixture["jobs"])

    for name, expected in (
        ("test (ubuntu-latest, 3.14)", ubuntu_timings),
        ("masking gates (windows-latest)", windows_timings),
    ):
        jt = w.per_job[name]
        assert (jt.queue, jt.setup, jt.test, jt.teardown) == expected
