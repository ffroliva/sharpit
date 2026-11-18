"""Read the generated CLI tool manifest without importing the engine."""

import json
from dataclasses import dataclass
from importlib.resources import files


@dataclass(frozen=True)
class ManifestTool:
    name: str
    command: str
    flags: tuple[str, ...]
    panel: str
    action: bool
    summary: str
    description: str


@dataclass(frozen=True)
class Manifest:
    tools: tuple[ManifestTool, ...]

    @classmethod
    def bundled(cls) -> "Manifest":
        data = json.loads(files("sharpit.cli").joinpath("tools.json").read_text(encoding="utf-8"))
        return cls(
            tuple(
                ManifestTool(
                    name=item["name"],
                    command=item["command"],
                    flags=tuple(item["flags"]),
                    panel=item["panel"],
                    action=item["action"],
                    summary=item["summary"],
                    description=item["description"],
                )
                for item in data["tools"]
            )
        )

    def by_name(self, name: str) -> ManifestTool:
        return next(tool for tool in self.tools if tool.name == name)
