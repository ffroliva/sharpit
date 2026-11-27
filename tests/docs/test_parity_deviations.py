"""Verify that the deviations sections in docs/reference/PARITY.md match the matrix fragments."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from scripts.dev import generate_parity_deviations as parity


def test_parity_md_contains_current_deviations_sections() -> None:
    content = parity.PARITY_MD.read_text(encoding="utf-8")
    headings = [heading for heading, _ in parity._RELEASES.values()]
    for heading in headings:
        assert heading in content, f"{heading} missing in {parity.PARITY_MD.name}"

    sections = re.split(r"(?m)(?=^## \d+\.\d+\.\d+ against BootUI )", content)[1:]
    assert [section.splitlines()[0] for section in sections] == headings
    for release, section in zip(parity._RELEASES, sections, strict=True):
        assert section.strip() == parity.generate_section(release=release).strip(), release


@pytest.mark.parametrize("release", parity._RELEASES)
def test_every_fragment_row_is_categorized(release: str) -> None:
    _, fragments = parity._RELEASES[release]
    deviations = parity.collect_deviations(fragments=fragments)
    counts = {"0.7.0": 117, "0.8.0": 116, "0.10.0": 46}
    if release in counts:
        assert len(deviations) == counts[release]

    expected = []
    for lane, filename in fragments:
        filepath = parity.MATRIX_UPDATES / filename
        assert filepath.is_file(), f"Missing fragment {filename}"
        for line in filepath.read_text(encoding="utf-8").splitlines():
            if line.strip():
                fields = line.split("\t")
                assert len(fields) >= 2, f"Malformed line in {filename}: {line}"
                key, status, *reason = fields
                if status != "matched":
                    expected.append(parity.DeviationRow(lane, key, status, reason[0] if reason else ""))
    assert deviations == expected


def test_dev_service_logs_are_deferred() -> None:
    _, fragments = parity._RELEASES["0.10.0"]
    statuses = [
        row.status
        for row in parity.collect_deviations(fragments=fragments)
        if row.key == "route:GET /dev-services/{id}/logs"
    ]
    assert statuses == ["deferred"]


def test_default_heading_matches_the_release() -> None:
    assert parity.generate_section(release="0.10.0").startswith(f"{parity.SECTION_HEADING_0_10_0}\n")


def test_update_parity_accepts_explicit_0_10_0_rows(tmp_path: Path) -> None:
    document = tmp_path / "PARITY.md"
    document.write_text("# Parity\n", encoding="utf-8")
    row = parity.DeviationRow("example", "parity-key", "adapted", "Explicit release row")
    try:
        content = parity.update_parity_md(document, rows_0_10_0=[row])
    except TypeError:
        content = ""
    assert "| example | parity-key | adapted | Explicit release row |" in content


@pytest.mark.parametrize("release", parity._RELEASES)
def test_check_names_the_release_with_drift(
    release: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    content = parity.PARITY_MD.read_text(encoding="utf-8")
    heading, _ = parity._RELEASES[release]
    document = tmp_path / "PARITY.md"
    document.write_text(content.replace(f"{heading}\n", f"{heading}\n\nUnexpected text\n", 1), encoding="utf-8")
    monkeypatch.setattr(parity, "PARITY_MD", document)
    monkeypatch.setattr(sys, "argv", ["generate_parity_deviations.py", "--check"])

    assert parity.main() == 1
    assert f"{release} deviation section" in capsys.readouterr().out
