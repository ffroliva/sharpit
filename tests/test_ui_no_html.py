"""No ``{@html`` anywhere in the UI sources: a captured value is always rendered as text (spec §7)."""

from pathlib import Path

UI_SRC = Path(__file__).parents[1] / "ui" / "src"


def test_no_raw_html_in_views() -> None:
    if not UI_SRC.is_dir():  # the sdist ships no ui/
        return
    files = sorted(UI_SRC.rglob("*.svelte"))
    assert files, "no .svelte files found: the path is wrong"
    assert [str(f.relative_to(UI_SRC)) for f in files if "{@html" in f.read_text(encoding="utf-8")] == []
