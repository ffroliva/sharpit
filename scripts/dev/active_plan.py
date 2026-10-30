#!/usr/bin/env python3
"""Print a compact summary of the active implementation plan (ported from gflow-cli).

Plans are flat dated files ``docs/superpowers/plans/YYYY-MM-DD-<slug>.md`` (a ``<date>-<slug>/PLAN.md``
directory also works). Selection:

1. ``--feature <slug>``: the newest plan whose path contains the slug.
2. Otherwise: the newest plan, by the date in its file name, that still has an unchecked ``- [ ]`` step.

Plans are ordered by file name, never by mtime: ``git checkout`` resets every mtime, so mtime says nothing
about which plan is current. Output is compact on purpose: only this chunk enters an agent's context.
Used by ``/sharpit:status``, ``/sharpit:next`` and ``/sharpit:active``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLANS_DIR = ROOT / "docs" / "superpowers" / "plans"

_UNCHECKED = re.compile(r"^\s*-\s*\[\s\]")
_CHECKED = re.compile(r"^\s*-\s*\[[xX]\]")
_TASK_HEADING = re.compile(r"^#{2,3}\s+(Task|Phase)\b")
_SECTION = re.compile(r"^#{2,3}\s+")


def candidates(plans_dir: Path = PLANS_DIR) -> list[Path]:
    """Every plan file, newest first by name (the date prefix sorts lexically)."""
    if not plans_dir.is_dir():
        return []
    found: list[Path] = []
    for p in plans_dir.iterdir():
        if p.is_file() and p.suffix == ".md":
            found.append(p)
        elif p.is_dir() and (p / "PLAN.md").is_file():
            found.append(p / "PLAN.md")
    return sorted(found, key=lambda p: p.parent.name if p.name == "PLAN.md" else p.name, reverse=True)


def _open_steps(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if _UNCHECKED.match(line))


def find_plan(feature: str | None, plans_dir: Path = PLANS_DIR) -> Path | None:
    plans = candidates(plans_dir)
    if feature:
        slug = feature.lower().replace(" ", "-").replace("_", "-")
        return next((p for p in plans if slug in p.as_posix().lower()), None)
    return next((p for p in plans if _open_steps(p)), None)


def summarise(path: Path, root: Path = ROOT) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    title = next((line.lstrip("# ").strip() for line in lines if line.startswith("# ")), path.stem)
    goal = next((line.replace("**Goal:**", "").strip() for line in lines if line.startswith("**Goal:**")), "")
    checked = sum(1 for line in lines if _CHECKED.match(line))
    unchecked = sum(1 for line in lines if _UNCHECKED.match(line))
    try:
        shown = path.relative_to(root).as_posix()
    except ValueError:
        shown = path.as_posix()
    header = [f"Plan : {shown}", f"Title: {title}"]
    if goal:
        header.append(f"Goal : {goal}")
    header.append(f"Progress: {checked}/{checked + unchecked} steps complete, {unchecked} remaining")

    first = next((i for i, line in enumerate(lines) if _UNCHECKED.match(line)), None)
    if first is None:
        return "\n".join(header) + "\n\nAll steps complete."
    start = next((j for j in range(first, -1, -1) if _TASK_HEADING.match(lines[j])), first)
    end = next((k for k in range(start + 1, len(lines)) if _SECTION.match(lines[k])), len(lines))
    block = "\n".join(lines[start:end]).rstrip()
    return "\n".join(header) + f"\n\n--- Next task ---\n{block}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the active plan summary (compact, for agent context).")
    parser.add_argument("--feature", "-f", metavar="SLUG", help="match against docs/superpowers/plans/ file names")
    args = parser.parse_args(argv)
    # Windows consoles default to cp1252; plans contain arrows and other non-ASCII text.
    if hasattr(sys.stdout, "reconfigure") and (sys.stdout.encoding or "").lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    plan = find_plan(args.feature)
    if plan is None:
        if args.feature:
            print(f"No plan in docs/superpowers/plans/ matches --feature {args.feature!r}.")
        else:
            print("No plan with open steps in docs/superpowers/plans/. Create one with /sharpit:plan <feature>.")
        return 1
    print(summarise(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
