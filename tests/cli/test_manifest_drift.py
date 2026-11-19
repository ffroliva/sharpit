"""Needs scripts/, which the sdist does not ship, so the sdist leaves this file out (pyproject, sdist exclude)."""

from pathlib import Path

from scripts.dev.gen_cli_manifest import generate


# ported: ToolManifestGeneratorTests.theCheckedInManifestMatchesTheCatalog
def test_manifest_matches_generation():
    checked_in = (Path(__file__).parents[2] / "src/sharpit/cli/tools.json").read_text(encoding="utf-8")
    assert checked_in == generate(), (
        "src/sharpit/cli/tools.json is stale; regenerate with `uv run python scripts/dev/gen_cli_manifest.py`"
    )
