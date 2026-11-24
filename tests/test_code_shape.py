"""Ratchets on code shape: they hold today's numbers and only let them go down. AGENTS.md "Architecture rules".

1. No module under ``src/`` passes ``MAX_LINES``.
2. Complexity: ruff C901 (McCabe > 10) findings per file are pinned in ``tests/complexity_baseline.json``. A file may
   not gain one, and a file that loses one must lower its entry in the same change, so the count can only fall.
3. Every Sonar suppression comment states its reason: ``NOSONAR - <why the refactor was rejected>``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAX_LINES = 1000
BASELINE = ROOT / "tests" / "complexity_baseline.json"
SUPPRESSION = "NO" + "SONAR"  # split, so this file holds no suppression of its own
EXPLAINED = re.compile(SUPPRESSION + r" - \S")
SCANNED = ("src/sharpit", "tests", "scripts", "ui/src")
SOURCE_SUFFIXES = {".py", ".ts", ".js", ".svelte"}


def oversized(root: Path = ROOT / "src", limit: int = MAX_LINES) -> list[str]:
    return [
        f"{path.relative_to(root).as_posix()}: {n} lines (max {limit})"
        for path in sorted(root.rglob("*.py"))
        if (n := len(path.read_text(encoding="utf-8").splitlines())) > limit
    ]


def complexity_counts() -> Counter[str]:
    pytest.importorskip("ruff")  # CI's lowest-direct job installs without the dev group; the other jobs run this
    out = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "C901", "--output-format", "json", "--exit-zero", "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return Counter(Path(f["filename"]).resolve().relative_to(ROOT).as_posix() for f in json.loads(out))


def ratchet_violations(found: Counter[str], pinned: dict[str, int]) -> list[str]:
    problems: list[str] = []
    for path in sorted(found.keys() | pinned.keys()):
        now, allowed = found.get(path, 0), pinned.get(path, 0)
        if now > allowed:
            problems.append(f"{path}: {now} functions over complexity 10 (pinned {allowed}); simplify, don't pin")
        elif now < allowed:
            problems.append(f"{path}: {now} functions over complexity 10, lower its entry from {allowed}")
    return problems


def unexplained_suppressions(root: Path = ROOT, dirs: tuple[str, ...] = SCANNED) -> list[str]:
    return [
        f"{path.relative_to(root).as_posix()}:{n}: {SUPPRESSION} needs ' - <reason>'"
        for top in dirs
        for path in sorted((root / top).rglob("*"))
        if path.suffix in SOURCE_SUFFIXES and path.is_file()
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
        if SUPPRESSION in line and not EXPLAINED.search(line)
    ]


def test_no_module_is_oversized():
    assert oversized() == []


def test_complexity_only_goes_down():
    assert ratchet_violations(complexity_counts(), json.loads(BASELINE.read_text(encoding="utf-8"))) == []


def test_every_suppression_states_its_reason():
    assert unexplained_suppressions() == []


def test_the_ratchets_catch_a_violation(tmp_path: Path) -> None:
    """Each ratchet fails on planted input, so a green run means the limits hold, not that nothing was checked."""
    (tmp_path / "big.py").write_text("x = 1\n" * 3, encoding="utf-8")
    (tmp_path / "small.py").write_text("x = 1\n", encoding="utf-8")
    assert oversized(tmp_path, limit=2) == ["big.py: 3 lines (max 2)"]

    pinned = {"a.py": 2, "b.py": 1}
    assert ratchet_violations(Counter({"a.py": 2, "b.py": 1}), pinned) == []
    assert [v.split(":")[0] for v in ratchet_violations(Counter({"a.py": 3, "b.py": 1, "c.py": 1}), pinned)] == [
        "a.py",
        "c.py",
    ]
    assert "lower its entry" in ratchet_violations(Counter({"a.py": 1, "b.py": 1}), pinned)[0]

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ok.py").write_text(f"x = 1  # {SUPPRESSION} - a reason\n", encoding="utf-8")
    (tmp_path / "src" / "bare.ts").write_text(f"let x = 1; // {SUPPRESSION}\n", encoding="utf-8")
    assert unexplained_suppressions(tmp_path, ("src",)) == [f"src/bare.ts:1: {SUPPRESSION} needs ' - <reason>'"]
