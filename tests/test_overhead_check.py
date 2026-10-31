from __future__ import annotations

import importlib.util
import json


def test_overhead_check_module_is_available():
    assert importlib.util.find_spec("scripts.dev.overhead_check") is not None


def test_classify_within_budget():
    from scripts.dev.overhead_check import classify

    assert classify([{"verdict": "ok", "overhead": 1.0, "budget": 2.0, "noise": 0.1}]) == "within budget"


def test_classify_failure_inside_noise_is_flaky():
    from scripts.dev.overhead_check import classify

    records = [
        {"verdict": "OVER", "overhead": 2.125, "budget": 2.0, "noise": 0.125},
        {"verdict": "ok", "overhead": 1.875, "budget": 2.0, "noise": 0.125},
    ]
    assert classify(records) == "flaky: failures are within the noise, suspect the machine, not the code"


def test_classify_failure_beyond_noise_is_over_budget():
    from scripts.dev.overhead_check import classify

    records = [{"verdict": "OVER", "overhead": 2.2, "budget": 2.0, "noise": 0.1}]
    assert classify(records) == "over budget: a failure is larger than its noise, treat as a real regression"


def test_read_records_parses_json_lines(tmp_path):
    from scripts.dev.overhead_check import read_records

    records = [
        {"name": "capture", "verdict": "ok", "budget": 0.2, "overhead": 0.12, "noise": 0.01},
        {"name": "sql", "verdict": "OVER", "budget": 0.3, "overhead": 0.4, "noise": 0.02},
    ]
    path = tmp_path / "overhead.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

    assert read_records(path) == records
