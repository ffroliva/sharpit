"""Tests for scripts/ci/ci_walls.py (W0b Task 1).

Verifies the attempt-1 critical path table reproduction from W0b-step0.md §2.1,
noise measurement, and the noise gain rule (after-max < before-min).
"""

from __future__ import annotations

import json
from pathlib import Path

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
    raised = False
    try:
        ci_walls.walls(bad_run, fixture["jobs"], REQUIRED)
    except ValueError:
        raised = True
    assert raised


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
