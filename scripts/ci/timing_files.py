"""Write the overhead budget test files (tests/_shard.py ``timing_files``) as pytest argument files, one per line.

    python scripts/ci/timing_files.py <dir>

``<dir>/budgets.args`` lists them (the budget step runs them alone, ``-n 0``); ``<dir>/no-budgets.args`` ignores them
(the parallel step), so every test still runs exactly once. Argument files keep the CI step free of shell expansion.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
from _shard import timing_files  # noqa: E402 - tests/ is no package; the planner is the single source


def main(out: Path) -> None:
    files = sorted(timing_files())
    out.mkdir(parents=True, exist_ok=True)
    (out / "budgets.args").write_text("".join(f"{rel}\n" for rel in files), encoding="utf-8")
    (out / "no-budgets.args").write_text("".join(f"--ignore={rel}\n" for rel in files), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
