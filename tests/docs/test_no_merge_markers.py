from __future__ import annotations

import re
import subprocess
from pathlib import Path


def test_tracked_markdown_has_no_merge_conflict_markers() -> None:
    root = Path(__file__).resolve().parents[2]
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"], cwd=root, check=True, capture_output=True
    ).stdout.split(b"\0")
    markers = re.compile(r"^(<<<<<<<|=======|>>>>>>>)( |$)", re.MULTILINE)
    found = [
        path.decode() for path in tracked if path and markers.search((root / path.decode()).read_text(encoding="utf-8"))
    ]
    assert not found, f"tracked Markdown contains merge conflict markers: {found}"
