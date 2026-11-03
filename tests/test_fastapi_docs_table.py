"""docs/fastapi-advisor-checks.md lists exactly the fastapi advisor's rules (BootUI ``SpringDocumentationTests``)."""

from __future__ import annotations

import re
from pathlib import Path

from sharpit.engine.collectors.fastapi_advisor.report import RULES

DOC = Path(__file__).resolve().parents[1] / "docs" / "fastapi-advisor-checks.md"
ROW = re.compile(r"^\| ((?:FASTAPI|SPRING)-[A-Z0-9-]+) \| (\w+) \| ([^|]+) \| ([^|]+) \|$")


def _rows() -> list[tuple[str, str, str, str]]:
    found: list[tuple[str, str, str, str]] = []
    for line in DOC.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match:
            rule, severity, category, title = match.groups()
            found.append((rule, severity, category.strip(), title.strip()))
    return found


def test_docs_table_matches_registry() -> None:
    expected = [(r.id, r.severity, r.category, r.name) for r in RULES]
    assert _rows() == expected
