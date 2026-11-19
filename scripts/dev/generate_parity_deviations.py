#!/usr/bin/env python3
"""Generate the 0.7.0 deviations table in docs/reference/PARITY.md from the matrix fragments."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
MATRIX_UPDATES = ROOT / "docs" / "reference" / "matrix-updates"
PARITY_MD = ROOT / "docs" / "reference" / "PARITY.md"

FRAGMENTS_0_7_0: list[tuple[str, str]] = [
    ("A1", "a1-counters.tsv"),
    ("A3", "a3-sec-static.tsv"),
    ("A4", "a4-db-advisor.tsv"),
    ("A5a", "a5a-journal.tsv"),
    ("A6", "a6-ui-readonly.tsv"),
    ("A7", "a7-exchange-recording.tsv"),
    ("B1", "b1-sql-kinds.tsv"),
    ("E1", "e1-65.tsv"),
    ("E2", "e2-66.tsv"),
    ("W0", "w0-pin-24.tsv"),
]

SECTION_HEADING = "## 0.7.0 against BootUI 2.4.0: deviations"


class DeviationRow(NamedTuple):
    lane: str
    key: str
    status: str
    reason: str


def collect_deviations(
    matrix_dir: Path = MATRIX_UPDATES,
    fragments: list[tuple[str, str]] = FRAGMENTS_0_7_0,
) -> list[DeviationRow]:
    rows: list[DeviationRow] = []
    for lane, filename in fragments:
        filepath = matrix_dir / filename
        if not filepath.is_file():
            continue
        text = filepath.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                key = parts[0]
                status = parts[1]
                reason = parts[2] if len(parts) > 2 else ""
                if status != "matched":
                    rows.append(DeviationRow(lane=lane, key=key, status=status, reason=reason))
    return rows


def generate_table(rows: list[DeviationRow]) -> str:
    lines = [
        "| Lane | Key | Status | Reason |",
        "|---|---|---|---|",
    ]
    for r in rows:
        escaped_reason = r.reason.replace("|", "\\|")
        lines.append(f"| {r.lane} | {r.key} | {r.status} | {escaped_reason} |")
    return "\n".join(lines)


def generate_section(rows: list[DeviationRow] | None = None) -> str:
    if rows is None:
        rows = collect_deviations()
    table = generate_table(rows)
    return (
        f"{SECTION_HEADING}\n\n"
        "Every deviation, partial implementation, adapted behavior, gap, or not-applicable item recorded across\n"
        f"the 0.7.0 lane fragments in `docs/reference/matrix-updates/` ({len(rows)} entries):\n\n"
        f"{table}\n"
    )


def update_parity_md(parity_path: Path = PARITY_MD, rows: list[DeviationRow] | None = None) -> str:
    section = generate_section(rows)
    content = parity_path.read_text(encoding="utf-8")
    if SECTION_HEADING in content:
        prefix = content.split(SECTION_HEADING, 1)[0].rstrip()
        new_content = f"{prefix}\n\n{section}"
    else:
        new_content = f"{content.rstrip()}\n\n{section}"
    parity_path.write_text(new_content, encoding="utf-8")
    return new_content


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check if PARITY.md matches fragments")
    parser.add_argument("--write", action="store_true", help="Update PARITY.md with generated section")
    args = parser.parse_args()

    rows = collect_deviations()
    section = generate_section(rows)

    if args.write:
        update_parity_md(rows=rows)
        print(f"Updated {PARITY_MD.relative_to(ROOT)} with {len(rows)} deviation rows.")
        return 0

    if args.check:
        content = PARITY_MD.read_text(encoding="utf-8")
        if SECTION_HEADING not in content:
            print(f"FAIL: {SECTION_HEADING} not found in {PARITY_MD.name}")
            return 1
        current_section = SECTION_HEADING + content.split(SECTION_HEADING, 1)[1]
        if current_section.strip() != section.strip():
            print(f"FAIL: {PARITY_MD.name} does not match generated section")
            return 1
        print(f"PASS: {PARITY_MD.name} matches generated section ({len(rows)} rows)")
        return 0

    print(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
