"""``docs/security-advisor-checks.md`` matches the rule registry (port of BootUI ``SecurityDocumentationTests``)."""

from __future__ import annotations

import re
from pathlib import Path

from sharpit.engine.collectors.security.report import RULES

DOCS = Path(__file__).resolve().parents[1] / "docs" / "security-advisor-checks.md"
# BootUI 2.2.0 SecurityRuleRegistry.ACTIVE_RULES (servlet), in registry order
BOOTUI_IDS = [
    "SEC-AUTH-001",
    "SEC-AUTH-002",
    "SEC-AUTH-006",
    "SEC-AUTH-004",
    "SEC-AUTH-007",
    "SEC-AUTH-010",
    "SEC-AUTH-008",
    "SEC-AUTH-009",
    "SEC-AUTHZ-001",
    "SEC-AUTHZ-002",
    "SEC-AUTHZ-003",
    "SEC-AUTHZ-004",
    "SEC-AUTHZ-005",
    "SEC-CSRF-001",
    "SEC-CSRF-002",
    "SEC-SESSION-001",
    "SEC-SESSION-002",
    "SEC-SESSION-003",
    "SEC-SESSION-004",
    "SEC-SESSION-006",
    "SEC-SESSION-007",
    "SEC-SESSION-008",
    "SEC-HEAD-001",
    "SEC-HEAD-002",
    "SEC-HEAD-003",
    "SEC-HEAD-004",
    "SEC-HEAD-007",
    "SEC-HEAD-008",
    "SEC-HEAD-009",
    "SEC-HEAD-010",
    "SEC-CORS-001",
    "SEC-CORS-002",
    "SEC-CORS-006",
    "SEC-METHOD-001",
    "SEC-METHOD-002",
    "SEC-ACT-001",
    "SEC-ACT-002",
    "SEC-ACT-003",
    "SEC-ACT-004",
    "SEC-ACT-005",
    "SEC-ACT-006",
    "SEC-ACT-007",
    "SEC-OAUTH-002",
    "SEC-OAUTH-003",
    "SEC-OAUTH-004",
    "SEC-OAUTH-005",
    "SEC-OAUTH-006",
    "SEC-CONFIG-001",
    "SEC-CONFIG-002",
    "SEC-CONFIG-005",
    "SEC-CONFIG-006",
    "SEC-CONFIG-007",
    "SEC-CONFIG-008",
    "SEC-CONFIG-009",
]
_ROW = re.compile(r"^\| (SEC-[A-Z]+-\d+) \| (.+?) \| (.+?) \| (CRITICAL|HIGH|MEDIUM|LOW|INFO) \| ([PND]) \| (.*) \|$")


def _rows() -> dict[str, tuple[str, str, str, str, str]]:
    rows: dict[str, tuple[str, str, str, str, str]] = {}
    for line in DOCS.read_text(encoding="utf-8").splitlines():
        if match := _ROW.match(line):
            rule_id, title, category, severity, port, trigger = match.groups()
            rows[rule_id] = (title, category, severity, port, trigger.strip())
    return rows


def test_docs_table_matches_registry():
    # ported: SecurityDocumentationTests (the checks table lists exactly the registry's rules)
    rows = _rows()
    active = {rule_id: row[:3] for rule_id, row in rows.items() if row[3] in "PN"}
    registry = {r.definition.id: (r.definition.name, r.definition.category, r.definition.severity) for r in RULES}
    assert active == registry


def test_every_bootui_rule_has_a_row():
    rows = _rows()
    assert [rule_id for rule_id in BOOTUI_IDS if rule_id not in rows] == []


def test_dropped_and_new_rows_say_why():
    rows = _rows()
    unexplained = [rule_id for rule_id, row in rows.items() if not row[4]]
    new_with_bootui_id = [rule_id for rule_id, row in rows.items() if row[3] == "N" and rule_id in BOOTUI_IDS]
    assert unexplained == []
    assert new_with_bootui_id == []
