"""Verify that the deviations sections in docs/reference/PARITY.md match the matrix fragments."""

from __future__ import annotations

from pathlib import Path

from scripts.dev.generate_parity_deviations import (
    FRAGMENTS_0_7_0,
    FRAGMENTS_0_8_0,
    MATRIX_UPDATES,
    PARITY_MD,
    SECTION_HEADING_0_7_0,
    SECTION_HEADING_0_8_0,
    collect_deviations,
    generate_section_0_7_0,
    generate_section_0_8_0,
)

ROOT = Path(__file__).resolve().parents[2]


def test_parity_md_contains_current_deviations_sections():
    content = PARITY_MD.read_text(encoding="utf-8")
    assert SECTION_HEADING_0_7_0 in content, f"{SECTION_HEADING_0_7_0} missing in {PARITY_MD.name}"
    assert SECTION_HEADING_0_8_0 in content, f"{SECTION_HEADING_0_8_0} missing in {PARITY_MD.name}"

    parts = content.split(SECTION_HEADING_0_7_0, 1)[1].split(SECTION_HEADING_0_8_0, 1)
    current_0_7_0 = (SECTION_HEADING_0_7_0 + parts[0]).strip()
    current_0_8_0 = (SECTION_HEADING_0_8_0 + parts[1]).strip()

    expected_0_7_0 = generate_section_0_7_0().strip()
    expected_0_8_0 = generate_section_0_8_0().strip()

    assert current_0_7_0 == expected_0_7_0, (
        f"{PARITY_MD.name} 0.7.0 deviations section has drifted from fragments in {MATRIX_UPDATES.name}.\n"
        "Run: uv run python scripts/dev/generate_parity_deviations.py --write"
    )
    assert current_0_8_0 == expected_0_8_0, (
        f"{PARITY_MD.name} 0.8.0 deviations section has drifted from fragments in {MATRIX_UPDATES.name}.\n"
        "Run: uv run python scripts/dev/generate_parity_deviations.py --write"
    )


def test_every_fragment_row_is_categorized():
    deviations_0_7_0 = collect_deviations(fragments=FRAGMENTS_0_7_0)
    assert len(deviations_0_7_0) == 117

    for lane, filename in FRAGMENTS_0_7_0:
        filepath = MATRIX_UPDATES / filename
        assert filepath.is_file(), f"Missing fragment {filename}"
        lines = [line.strip() for line in filepath.read_text(encoding="utf-8").splitlines() if line.strip()]
        for line in lines:
            parts = line.split("\t")
            assert len(parts) >= 2, f"Malformed line in {filename}: {line}"
            key, status = parts[0], parts[1]
            if status != "matched":
                assert any(d.key == key and d.lane == lane for d in deviations_0_7_0)

    deviations_0_8_0 = collect_deviations(fragments=FRAGMENTS_0_8_0)
    assert len(deviations_0_8_0) == 79

    for lane, filename in FRAGMENTS_0_8_0:
        filepath = MATRIX_UPDATES / filename
        assert filepath.is_file(), f"Missing fragment {filename}"
        lines = [line.strip() for line in filepath.read_text(encoding="utf-8").splitlines() if line.strip()]
        for line in lines:
            parts = line.split("\t")
            assert len(parts) >= 2, f"Malformed line in {filename}: {line}"
            key, status = parts[0], parts[1]
            if status != "matched":
                assert any(d.key == key and d.lane == lane for d in deviations_0_8_0)
