#!/usr/bin/env python3
"""Compare Playwright screenshot folders by content hash: did a change alter a pixel?

Usage: compare_shots.py <before-1> <before-2> <after>

Two runs of the same code (``before-1``, ``before-2``) show which screenshots move on their own (live data, clocks):
those are "live" and are printed to check by eye. Any other file whose hash differs in ``after``, or that is
missing there, is a regression and the exit code is 1.
"""

import hashlib
import sys
from pathlib import Path


def _hashes(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}


def main(before_1: Path, before_2: Path, after: Path) -> int:
    first, second, now = _hashes(before_1), _hashes(before_2), _hashes(after)
    live = sorted(name for name in first if first[name] != second.get(name))
    stable = [name for name in first if name not in live]
    regressions = [name for name in stable if now.get(name) != first[name]]
    for name in live:
        print(f"live (check by eye): {name}")
    for name in regressions:
        print(f"{'MISSING' if name not in now else 'CHANGED'}: {name}")
    print(f"{len(stable)} stable, {len(live)} live, {len(regressions)} regressions")
    return 1 if regressions else 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    sys.exit(main(*(Path(a) for a in sys.argv[1:])))
