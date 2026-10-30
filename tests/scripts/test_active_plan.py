"""scripts/dev/active_plan.py: plan selection and the next-task block."""

from pathlib import Path

import pytest
from _load import load_script

active_plan = load_script("scripts/dev/active_plan.py")

PLAN = """# Widget Implementation Plan

**Goal:** Ship the widget.

### Task 1: Scaffold

- [x] **Step 1:** done

### Task 2: Core

- [ ] **Step 1:** write the failing test
- [ ] **Step 2:** make it pass

### Task 3: Docs

- [ ] **Step 1:** README
"""


def _write(d: Path, name: str, body: str) -> Path:
    p = d / name
    p.write_text(body, encoding="utf-8")
    return p


def test_default_picks_newest_dated_plan_with_open_steps(tmp_path: Path) -> None:
    _write(tmp_path, "2026-10-01-old.md", PLAN)
    _write(tmp_path, "2026-12-01-finished.md", "# Done\n\n- [x] all\n")
    newest_open = _write(tmp_path, "2026-11-01-widget.md", PLAN)
    assert active_plan.find_plan(None, tmp_path) == newest_open


def test_feature_slug_matches_by_name(tmp_path: Path) -> None:
    old = _write(tmp_path, "2026-10-01-old-thing.md", PLAN)
    _write(tmp_path, "2026-11-01-widget.md", PLAN)
    assert active_plan.find_plan("old_thing", tmp_path) == old
    assert active_plan.find_plan("nope", tmp_path) is None


def test_scenario_notes_are_not_plans(tmp_path: Path) -> None:
    plan = _write(tmp_path, "2026-11-01-widget.md", PLAN)
    _write(tmp_path, "2026-11-01-widget-scenario.md", PLAN)
    assert active_plan.candidates(tmp_path) == [plan]


def test_directory_plans_are_found(tmp_path: Path) -> None:
    (tmp_path / "2026-11-02-dir").mkdir()
    plan = _write(tmp_path / "2026-11-02-dir", "PLAN.md", PLAN)
    assert active_plan.find_plan(None, tmp_path) == plan


def test_summary_shows_progress_and_next_task_only(tmp_path: Path) -> None:
    out = active_plan.summarise(_write(tmp_path, "2026-11-01-widget.md", PLAN), root=tmp_path)
    assert "Plan : 2026-11-01-widget.md" in out
    assert "Goal : Ship the widget." in out
    assert "Progress: 1/4 steps complete, 3 remaining" in out
    nxt = out.split("--- Next task ---\n", 1)[1]
    assert nxt.startswith("### Task 2: Core")
    assert "Task 3" not in nxt


def test_all_complete(tmp_path: Path) -> None:
    out = active_plan.summarise(_write(tmp_path, "2026-11-01-x.md", "# X\n\n- [x] a\n"), root=tmp_path)
    assert out.endswith("All steps complete.")


def test_main_reports_missing_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(active_plan, "PLANS_DIR", tmp_path)
    monkeypatch.setattr(active_plan.find_plan, "__defaults__", (tmp_path,))
    assert active_plan.main([]) == 1
