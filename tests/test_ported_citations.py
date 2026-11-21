"""BootUI test citations stay resolvable against the pinned source inventory."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "bootui" / "2.4.0" / "bootui-tests.json"
CITATION = re.compile(r"#\s*ported:\s*([\w$]+)\.([\w$]+)")


def _unresolved(citations: list[tuple[str, str]], inventory: dict[str, list[str]]) -> list[str]:
    methods = {name.rsplit(".", 1)[-1]: set(items) for name, items in inventory.items()}
    return [f"{class_name}.{method}" for class_name, method in citations if method not in methods.get(class_name, set())]


def test_ported_citations_resolve_in_bootui_test_inventory() -> None:
    inventory = json.loads(FIXTURE.read_text("utf-8"))["testClasses"]
    citations = [
        match.groups()
        for path in (ROOT / "tests").rglob("*.py")
        for match in CITATION.finditer(path.read_text("utf-8"))
    ]
    assert _unresolved(citations, inventory) == []


def test_unresolved_citation_names_the_missing_method() -> None:
    assert _unresolved([("PlantedTests", "missingMethod")], {"example.PlantedTests": ["presentMethod"]}) == [
        "PlantedTests.missingMethod"
    ]
