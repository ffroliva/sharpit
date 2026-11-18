"""Generate the packaged CLI command manifest from sharpit's tool catalogue."""

import json
import re
from pathlib import Path

from sharpit.engine.tools import COMMANDS, TOOLS


def generate() -> str:
    tools = []
    for tool in sorted(TOOLS, key=lambda item: COMMANDS[item.name]):
        flags = [
            re.sub(r"(?<!^)(?=[A-Z])", "-", name).replace("_", "-").lower()
            for name in tool.input_schema.get("properties", {})
        ]
        description = tool.description.strip()
        end = description.find(". ")
        tools.append(
            {
                "name": tool.name,
                "command": COMMANDS[tool.name],
                "flags": flags,
                "panel": tool.panel,
                "action": tool.action,
                "summary": description if end < 0 else description[: end + 1],
                "description": description,
            }
        )
    return json.dumps({"tools": tools}, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[2] / "src/sharpit/cli/tools.json"
    target.write_text(generate(), encoding="utf-8", newline="\n")
