"""Generate the packaged CLI command manifest from sharpit's tool catalogue (BootUI's ToolManifestGenerator)."""

import json
from pathlib import Path

from sharpit.engine.tools import _SCHEMA_NAMES, COMMANDS, TOOLS  # pyright: ignore[reportPrivateUsage]

TARGET = Path(__file__).resolve().parents[2] / "src/sharpit/cli/tools.json"


def _summary(description: str) -> str:
    """The first sentence, for the one-line command listing; the description itself is kept as written."""
    end = description.find(". ")
    return (description if end < 0 else description[: end + 1]).strip()


def _example(command: str, schema: str) -> str:
    line = f"sharpit {command}"
    if schema in {"ID", "OPTIONAL_ID", "RULE_VIOLATIONS"}:
        line += " <id>"
    if schema == "RULE_VIOLATIONS":
        line += " --scan-id <scanId>"
    return line


def generate() -> str:
    tools = []
    for tool in sorted(TOOLS, key=lambda item: COMMANDS[item.name]):
        arguments = tuple(tool.input_schema.get("properties", {}))
        schema = _SCHEMA_NAMES[arguments]
        tools.append(
            {
                "name": tool.name,
                "command": COMMANDS[tool.name],
                "schema": schema,
                "panel": tool.panel,
                "action": tool.action,
                "summary": _summary(tool.description),
                "description": tool.description,
                "example": _example(COMMANDS[tool.name], schema),
                "arguments": list(arguments),
                "required": list(tool.input_schema.get("required", [])),
            }
        )
    return json.dumps({"tools": tools}, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    TARGET.write_text(generate(), encoding="utf-8", newline="\n")
