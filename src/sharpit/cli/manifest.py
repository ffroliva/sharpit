"""Read the generated CLI tool manifest without importing the engine."""

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any


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
        return cls(tuple(ManifestTool(**item) for item in data["tools"]))

    def by_name(self, name: str) -> ManifestTool:
        return next(tool for tool in self.tools if tool.name == name)
