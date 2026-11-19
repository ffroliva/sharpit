import re
from pathlib import Path

from sharpit.engine.guard import PANEL_ACCESS_DENIED


def test_panel_access_denied_constant_matches_ui() -> None:
    api_ts = Path(__file__).resolve().parents[2] / "ui" / "src" / "lib" / "api.ts"
    content = api_ts.read_text(encoding="utf-8")
    match = re.search(r"export const PANEL_ACCESS_DENIED\s*=\s*['\"]([^'\"]+)['\"];", content)
    assert match is not None, "PANEL_ACCESS_DENIED not found in ui/src/lib/api.ts"
    assert match.group(1) == PANEL_ACCESS_DENIED
