"""SkillOpt harness: scoring, dataset shape and dry run only. No test calls an API."""

import json
from pathlib import Path

import pytest
from _load import load_script

harness = load_script("scripts/dev/skillopt/harness.py")
score = harness.score_response


def test_threshold_is_not_lost_to_float_accumulation() -> None:
    # 1.0 - 0.3 + 0.1 == 0.7999999999999999 unrounded; a printed 0.80 must grade PASS.
    s, _ = score(
        "install(app); bad; extra",
        {"must_include": ["install(app)"], "must_not_include": ["bad"], "partial_credit": ["extra"]},
    )
    assert s == 0.8
    assert harness.grade(s) == "PASS"


def test_full_marks_and_reasons() -> None:
    assert score("SHARPIT_READ_ONLY=true", {"must_include": ["sharpit_read_only"]}) == (1.0, [])
    s, reasons = score("nothing", {"must_include": ["a", "b"]})
    assert s == 0.0
    assert reasons == ["MISS: ['a', 'b']"]


def test_penalty_cap_and_bonus_cap() -> None:
    s, _ = score("ok b0 b1 b2 b3", {"must_include": ["ok"], "must_not_include": [f"b{i}" for i in range(4)]})
    assert s == pytest.approx(0.1)
    s, _ = score("x p0 p1 p2 p3", {"must_include": ["x", "y"], "partial_credit": [f"p{i}" for i in range(4)]})
    assert s == 0.8  # 0.5 base + 0.3 capped bonus


def test_grades() -> None:
    assert [harness.grade(x) for x in (1.0, 0.8, 0.79, 0.4, 0.39)] == ["PASS", "PASS", "PARTIAL", "PARTIAL", "FAIL"]


def test_errors_are_excluded_from_the_average() -> None:
    rows = [
        {"id": "a", "tags": ["t"], "score": 1.0, "status": "PASS", "reasons": []},
        {"id": "b", "tags": ["t"], "score": 0.0, "status": "ERROR", "reasons": ["ERROR: HTTP 429"]},
    ]
    out = harness.summarise(rows)
    assert "SUMMARY: 1/1 passed  avg score 1.000" in out
    assert "1 of 2 task(s) did not complete" in out
    assert "no task completed" in harness.summarise(rows[1:])


def test_dataset_shape() -> None:
    tasks = json.loads(harness.TASKS_PATH.read_text(encoding="utf-8"))
    assert 10 <= len(tasks) <= 20
    assert len({t["id"] for t in tasks}) == len(tasks)
    for t in tasks:
        assert t["question"] and t["tags"] and t["expected"]["must_include"], t["id"]
        assert set(t["expected"]) <= {"must_include", "must_not_include", "partial_credit"}, t["id"]


def test_base_url_must_be_https_or_loopback() -> None:
    assert harness.check_base_url("https://api.example/v1/") == "https://api.example/v1"
    assert harness.check_base_url("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434/v1"
    with pytest.raises(SystemExit):
        harness.check_base_url("http://gateway.example/v1")


def test_dry_run_prints_every_task_without_network(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_network(*_a: object, **_k: object) -> None:
        raise AssertionError("dry run must not call the API")

    monkeypatch.setattr(harness, "_call_llm", no_network)
    assert harness.main(["--dry-run", "--tags", "mcp"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN - 2 task(s)" in out
    assert "[mcp-001]" in out and "[mcp-002]" in out


def test_skill_frontmatter_is_read() -> None:
    _, version, epoch = harness.load_skill(Path(harness.DEFAULT_SKILL_PATH))
    assert version != "unknown"
    assert epoch == 0
