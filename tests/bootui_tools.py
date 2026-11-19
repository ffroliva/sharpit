"""The BootUI 2.3.0 tool catalogue fixture, loaded once for every test that compares against it."""

import json
from pathlib import Path

BOOTUI_TOOLS = json.loads((Path(__file__).parent / "fixtures/bootui/2.3.0/tools.json").read_text("utf-8"))["tools"]
BOOTUI = {tool["name"]: tool for tool in BOOTUI_TOOLS}
