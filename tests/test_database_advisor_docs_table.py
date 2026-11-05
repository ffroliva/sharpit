"""``docs/database-advisor-checks.md`` lists BootUI's 48 checks; its implemented rows are exactly the registry."""

from __future__ import annotations

import re
from pathlib import Path

from sharpit.engine.collectors.database_advisor import RULES

DOC = Path(__file__).resolve().parents[1] / "docs" / "database-advisor-checks.md"
_ROW = re.compile(r"^\| (DB-[A-Z]+-\d{3}) \| (.+?) \| (.+?) \| (P|dropped) \| (.+?) \|(.*)\|$")


def _rows() -> list[tuple[str, ...]]:
    return [m.groups() for line in DOC.read_text(encoding="utf-8").splitlines() if (m := _ROW.match(line))]


def test_docs_table_matches_registry() -> None:
    rows = _rows()
    implemented = sorted(rule_id for rule_id, *_rest, status, _reason in rows if status == "implemented")

    assert len(rows) == 48
    assert sum(1 for row in rows if row[3] == "P") == 33
    assert implemented == sorted(r.definition.id for r in RULES)


def test_dropped_checks_give_a_reason() -> None:
    missing = [row[0] for row in _rows() if row[3] == "dropped" and not row[5].strip()]

    assert missing == []


def test_docs_titles_match_registry_names() -> None:
    titles = {row[0]: row[1] for row in _rows()}

    assert {r.definition.id: r.definition.name for r in RULES} == {
        r.definition.id: titles[r.definition.id] for r in RULES
    }
