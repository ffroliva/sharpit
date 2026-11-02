"""Fail a PR into main that still tracks files under .superpowers/ (agent coordination evidence).

Lane branches commit their evidence because scripts/dev/lane_gate.py reads it from git; main never carries it.
Harvest the run's decisions into docs/reports/ first, then `git rm -r --cached .superpowers/` (docs/development/
workflow.md, step 7). CI runs this only when the pull request's base is main.
"""

from __future__ import annotations

import subprocess
import sys

PREFIX = ".superpowers/"


def tracked(paths: list[str]) -> list[str]:
    """The paths that live under .superpowers/."""
    return []


def main() -> int:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True, check=True).stdout
    found = tracked([p for p in out.split("\0") if p])
    if found:
        print(f"{len(found)} file(s) under {PREFIX} are tracked; harvest decisions into docs/reports/, then")
        print(f"  git rm -r --cached {PREFIX}")
        for path in found[:20]:
            print(f"  {path}")
        return 1
    print(f"no tracked files under {PREFIX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
