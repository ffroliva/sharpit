"""Verify that the 0.7.0 deviations section in docs/reference/PARITY.md matches the matrix fragments."""

from __future__ import annotations

from pathlib import Path

from scripts.dev.generate_parity_deviations import (
    FRAGMENTS_0_7_0,
    MATRIX_UPDATES,
    PARITY_MD,
    SECTION_HEADING,
    collect_deviations,
    generate_section,
)

ROOT = Path(__file__).resolve().parents[2]


def test_parity_md_contains_current_deviations_section():
    content = PARITY_MD.read_text(encoding="utf-8")
    assert SECTION_HEADING in content, f"{SECTION_HEADING} missing in {PARITY_MD.name}"

    current_section = SECTION_HEADING + content.split(SECTION_HEADING, 1)[1]
    expected_section = generate_section()
    assert current_section.strip() == expected_section.strip(), (
        f"{PARITY_MD.name} 0.7.0 deviations section has drifted from fragments in {MATRIX_UPDATES.name}.\n"
        "Run: uv run python scripts/dev/generate_parity_deviations.py --write"
    )


def test_every_fragment_row_is_categorized():
    deviations = collect_deviations()
    assert len(deviations) == 117

    for lane, filename in FRAGMENTS_0_7_0:
        filepath = MATRIX_UPDATES / filename
        assert filepath.is_file(), f"Missing fragment {filename}"
        lines = [line.strip() for line in filepath.read_text(encoding="utf-8").splitlines() if line.strip()]
        for line in lines:
            parts = line.split("\t")
            assert len(parts) >= 2, f"Malformed line in {filename}: {line}"
            key, status = parts[0], parts[1]
            if status != "matched":
                assert any(d.key == key and d.lane == lane for d in deviations)
