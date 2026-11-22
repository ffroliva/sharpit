#!/usr/bin/env python3
"""Generate the parity deviations tables in docs/reference/PARITY.md from the matrix fragments."""

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
    ("C", "cli-t2.tsv"),
    ("C", "cli-t3.tsv"),
    ("C", "cli-t4.tsv"),
    ("C", "cli-t5.tsv"),
    ("C", "cli-t6.tsv"),
    ("C", "cli-t7.tsv"),
    ("C", "cli-t8.tsv"),
    ("E1", "e1-65.tsv"),
    ("E2", "e2-66.tsv"),
    ("G1", "g1-playbooks.tsv"),
    ("G2", "g2-prompts.tsv"),
    ("W0", "w0-pin-24.tsv"),
]

FRAGMENTS_0_8_0: list[tuple[str, str]] = [
    ("A1", "0.8.0-a1.tsv"),
    ("A2", "0.8.0-a2.tsv"),
    ("A3", "0.8.0-a3.tsv"),
    ("A4a", "0.8.0-a4a.tsv"),
    ("A5", "0.8.0-a5.tsv"),
    ("A6", "0.8.0-a6.tsv"),
    ("A7", "0.8.0-a7.tsv"),
    ("A8", "0.8.0-a8.tsv"),
    ("A9", "0.8.0-a9.tsv"),
    ("A10", "0.8.0-a10.tsv"),
    ("A11", "0.8.0-a11.tsv"),
    ("A12", "0.8.0-a12.tsv"),
    ("A13", "0.8.0-a13.tsv"),
    ("F1", "0.8.0-f1.tsv"),
    ("T1", "0.8.0-t1.tsv"),
    ("W0b", "0.8.0-w0b.tsv"),
    ("SHIPFIX", "0.8.0-shipfix.tsv"),
]

FRAGMENTS_0_9_0: list[tuple[str, str]] = [
    ("M1", "0.9.0-m1.tsv"),
    ("M2", "0.9.0-m2.tsv"),
    ("R0", "0.9.0-r0.tsv"),
    ("S3/S4", "0.9.0-s34.tsv"),
]

SECTION_HEADING_0_7_0 = "## 0.7.0 against BootUI 2.4.0: deviations"
SECTION_HEADING_0_8_0 = "## 0.8.0 against BootUI 2.5.0: deviations"
SECTION_HEADING_0_9_0 = "## 0.9.0 against BootUI 2.5.0: deviations"


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


def generate_section(
    rows: list[DeviationRow] | None = None,
    heading: str = SECTION_HEADING_0_7_0,
    release: str = "0.7.0",
) -> str:
    if rows is None:
        if release == "0.7.0":
            fragments = FRAGMENTS_0_7_0
        elif release == "0.8.0":
            fragments = FRAGMENTS_0_8_0
        else:
            fragments = FRAGMENTS_0_9_0
        rows = collect_deviations(fragments=fragments)
    table = generate_table(rows)
    return (
        f"{heading}\n\n"
        f"Every deviation, partial implementation, adapted behavior, gap, or not-applicable item recorded across\n"
        f"the {release} lane fragments in `docs/reference/matrix-updates/` ({len(rows)} entries):\n\n"
        f"{table}\n"
    )


def generate_section_0_7_0(rows: list[DeviationRow] | None = None) -> str:
    return generate_section(rows=rows, heading=SECTION_HEADING_0_7_0, release="0.7.0")


def generate_section_0_8_0(rows: list[DeviationRow] | None = None) -> str:
    return generate_section(rows=rows, heading=SECTION_HEADING_0_8_0, release="0.8.0")


def generate_section_0_9_0(rows: list[DeviationRow] | None = None) -> str:
    return generate_section(rows=rows, heading=SECTION_HEADING_0_9_0, release="0.9.0")


def update_parity_md(
    parity_path: Path = PARITY_MD,
    rows_0_7_0: list[DeviationRow] | None = None,
    rows_0_8_0: list[DeviationRow] | None = None,
    rows_0_9_0: list[DeviationRow] | None = None,
) -> str:
    sec_0_7_0 = generate_section_0_7_0(rows_0_7_0)
    sec_0_8_0 = generate_section_0_8_0(rows_0_8_0)
    sec_0_9_0 = generate_section_0_9_0(rows_0_9_0)
    content = parity_path.read_text(encoding="utf-8")
    if SECTION_HEADING_0_7_0 in content:
        prefix = content.split(SECTION_HEADING_0_7_0, 1)[0].rstrip()
        new_content = f"{prefix}\n\n{sec_0_7_0}\n{sec_0_8_0}\n{sec_0_9_0}"
    else:
        new_content = f"{content.rstrip()}\n\n{sec_0_7_0}\n{sec_0_8_0}\n{sec_0_9_0}"
    parity_path.write_text(new_content, encoding="utf-8", newline="\n")
    return new_content


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check if PARITY.md matches fragments")
    parser.add_argument("--write", action="store_true", help="Update PARITY.md with generated sections")
    args = parser.parse_args()

    rows_0_7_0 = collect_deviations(fragments=FRAGMENTS_0_7_0)
    rows_0_8_0 = collect_deviations(fragments=FRAGMENTS_0_8_0)
    rows_0_9_0 = collect_deviations(fragments=FRAGMENTS_0_9_0)

    if args.write:
        update_parity_md(rows_0_7_0=rows_0_7_0, rows_0_8_0=rows_0_8_0, rows_0_9_0=rows_0_9_0)
        print(
            f"Updated {PARITY_MD.relative_to(ROOT)} with {len(rows_0_7_0)} (0.7.0), "
            f"{len(rows_0_8_0)} (0.8.0), and {len(rows_0_9_0)} (0.9.0) deviation rows."
        )
        return 0

    if args.check:
        content = PARITY_MD.read_text(encoding="utf-8")
        if SECTION_HEADING_0_7_0 not in content:
            print(f"FAIL: {SECTION_HEADING_0_7_0} not found in {PARITY_MD.name}")
            return 1
        if SECTION_HEADING_0_8_0 not in content:
            print(f"FAIL: {SECTION_HEADING_0_8_0} not found in {PARITY_MD.name}")
            return 1
        if SECTION_HEADING_0_9_0 not in content:
            print(f"FAIL: {SECTION_HEADING_0_9_0} not found in {PARITY_MD.name}")
            return 1

        parts_0_7 = content.split(SECTION_HEADING_0_7_0, 1)[1].split(SECTION_HEADING_0_8_0, 1)
        current_0_7_0 = (SECTION_HEADING_0_7_0 + parts_0_7[0]).strip()
        parts_0_8 = parts_0_7[1].split(SECTION_HEADING_0_9_0, 1)
        current_0_8_0 = (SECTION_HEADING_0_8_0 + parts_0_8[0]).strip()
        current_0_9_0 = (SECTION_HEADING_0_9_0 + parts_0_8[1]).strip()

        expected_0_7_0 = generate_section_0_7_0(rows_0_7_0).strip()
        expected_0_8_0 = generate_section_0_8_0(rows_0_8_0).strip()
        expected_0_9_0 = generate_section_0_9_0(rows_0_9_0).strip()

        if current_0_7_0 != expected_0_7_0:
            print(f"FAIL: {PARITY_MD.name} 0.7.0 section does not match generated section")
            return 1
        if current_0_8_0 != expected_0_8_0:
            print(f"FAIL: {PARITY_MD.name} 0.8.0 section does not match generated section")
            return 1
        if current_0_9_0 != expected_0_9_0:
            print(f"FAIL: {PARITY_MD.name} 0.9.0 section does not match generated section")
            return 1

        print(
            f"PASS: {PARITY_MD.name} matches generated sections "
            f"({len(rows_0_7_0)} rows 0.7.0, {len(rows_0_8_0)} rows 0.8.0, {len(rows_0_9_0)} rows 0.9.0)"
        )
        return 0

    sec_0_7_0 = generate_section_0_7_0(rows_0_7_0)
    sec_0_8_0 = generate_section_0_8_0(rows_0_8_0)
    sec_0_9_0 = generate_section_0_9_0(rows_0_9_0)
    print(sec_0_7_0)
    print(sec_0_8_0)
    print(sec_0_9_0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
