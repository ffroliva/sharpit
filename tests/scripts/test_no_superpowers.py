"""scripts/ci/no_superpowers.py: a PR into main must not track .superpowers/ files."""

from _load import load_script

guard = load_script("scripts/ci/no_superpowers.py")


def test_tracked_evidence_is_reported() -> None:
    found = guard.tracked(["src/sharpit/__init__.py", ".superpowers/sdd/0.4.0/lanes/F/findings.md"])
    assert found == [".superpowers/sdd/0.4.0/lanes/F/findings.md"]


def test_a_clean_tree_passes() -> None:
    assert guard.tracked(["src/sharpit/__init__.py", "docs/reports/x.md"]) == []


def test_a_lookalike_name_is_not_evidence() -> None:
    assert guard.tracked(["docs/superpowers/specs/x.md", "x.superpowers/y"]) == []
