"""Verify no tracked documentation or skill file leaks local developer environment paths.

Checked roots:
- website/
- skills/
- plugins/

No tracked file may contain local home or worktree paths:
- Users\\<name> or /Users/
- /home/
- AppData
- sharpit-wt
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

LOCAL_PATH_PATTERNS = [
    re.compile(r"Users[/\\][A-Za-z0-9_.-]+"),
    re.compile(r"/Users/"),
    re.compile(r"/home/"),
    re.compile(r"AppData", re.IGNORECASE),
    re.compile(r"sharpit-wt"),
]


def _tracked_files() -> list[Path]:
    res = subprocess.run(
        ["git", "ls-files", "website", "skills", "plugins"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [ROOT / line.strip() for line in res.stdout.splitlines() if line.strip()]


def test_no_local_paths_in_tracked_docs_and_skills() -> None:
    files = _tracked_files()
    assert files, "No tracked files found under website/, skills/, or plugins/"

    violations: list[str] = []

    for file_path in files:
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        rel_path = file_path.relative_to(ROOT).as_posix()
        for idx, line in enumerate(content.splitlines(), start=1):
            if any(pattern.search(line) for pattern in LOCAL_PATH_PATTERNS):
                violations.append(f"{rel_path}:{idx}: {line.strip()[:100]}")

    assert not violations, f"Found {len(violations)} local path leaks in tracked files:\n" + "\n".join(violations)
