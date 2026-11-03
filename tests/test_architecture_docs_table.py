"""Tests matching the Architecture checks documentation table against the rule registry."""

from __future__ import annotations

from pathlib import Path

from sharpit.engine.collectors.architecture.rules import RULES


def test_docs_table_matches_registry() -> None:
    doc_path = Path("docs/architecture-advisor-checks.md")
    doc_ids: list[str] = []
    if doc_path.is_file():
        text = doc_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("|") and not line.startswith("|---"):
                parts = [p.strip() for p in line.split("|")[1:-1]]
                if parts and parts[0].startswith("ARCH-"):
                    doc_ids.append(parts[0])
    registry_ids = [r.id for r in RULES]
    assert doc_ids == registry_ids, (
        f"catalogue file {doc_path} is missing or has mismatched ids; found {doc_ids}, expected {registry_ids}"
    )
