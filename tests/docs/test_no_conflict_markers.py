"""No committed text file carries a merge-conflict marker."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]
MARKER = re.compile(r"^(<<<<<<<|=======|>>>>>>>)( |$)", re.MULTILINE)
SUFFIXES = {".md", ".py", ".toml", ".yml", ".yaml", ".tsv", ".json", ".txt", ".ts", ".svelte", ".cfg", ".ini"}


def _tracked() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True, text=True).stdout
    return [ROOT / name for name in out.split("\0") if name and Path(name).suffix in SUFFIXES]


def conflicted(root: Path, paths: list[Path]) -> list[str]:
    return [
        path.relative_to(root).as_posix()
        for path in paths
        if path.is_file() and MARKER.search(path.read_text(encoding="utf-8", errors="replace"))
    ]


def test_no_tracked_file_has_a_conflict_marker() -> None:
    assert conflicted(ROOT, _tracked()) == []


def test_a_planted_marker_is_found(tmp_path: Path) -> None:
    clean = tmp_path / "clean.md"
    clean.write_text("# Title\n\nA rule line follows.\n\n---\n", encoding="utf-8")
    planted = tmp_path / "CHANGELOG.md"
    planted.write_text("# Changelog\n<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> origin/release\n", encoding="utf-8")
    assert conflicted(tmp_path, [clean, planted]) == ["CHANGELOG.md"]
