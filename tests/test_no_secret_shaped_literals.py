"""Test fixtures build fake provider keys in pieces, never as one literal.

GitHub push protection blocks a push whose commits contain a full Stripe-shaped key, even a fake one used to prove
masking (0.4.0's release push was blocked this way). Write ``"sk_live_" + "a1b2..."`` instead: the test still sees a
full key at runtime, the source never holds one.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# built from pieces so this file never matches itself
KEY = re.compile("(sk|rk)" + "_(live|test)_" + "[A-Za-z0-9]{20,}")
SCANNED = ("tests", "src", "ui/src", "ui/tests", "docs", "examples")
SUFFIXES = {".py", ".ts", ".svelte", ".md", ".json", ".txt"}


def secret_shaped_literals(root: Path = ROOT) -> list[str]:
    found: list[str] = []
    for top in SCANNED:
        base = root / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in SUFFIXES or "node_modules" in path.parts or not path.is_file():
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if KEY.search(line):
                    found.append(f"{path.relative_to(root).as_posix()}:{n}")
    return found


def test_no_full_secret_shaped_literal_in_the_tree() -> None:
    assert secret_shaped_literals() == []


def test_the_scan_catches_a_planted_key(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text('KEY = "sk_' + "live_" + "a" * 24 + '"\n', encoding="utf-8")
    assert secret_shaped_literals(tmp_path) == ["tests/test_x.py:1"]
