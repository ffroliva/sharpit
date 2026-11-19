"""Read the generated CLI tool manifest without importing the engine (BootUI's ToolManifest)."""

import json
from dataclasses import dataclass, field
from importlib.resources import files


@dataclass(frozen=True)
class ManifestTool:
    name: str
    command: str
    schema: str
    panel: str
    action: bool
    summary: str
    description: str
    example: str
    arguments: tuple[str, ...]
    required: tuple[str, ...]

    @property
    def takes_scan_id(self) -> bool:
        return self._takes_scan_id

    @property
    def takes_offset(self) -> bool:
        return self._takes_scan_id

    @property
    def _takes_scan_id(self) -> bool:
        return self.schema == "RULE_VIOLATIONS"

    @property
    def takes_id(self) -> bool:
        return self.schema in {"ID", "OPTIONAL_ID"} or self.takes_scan_id

    @property
    def takes_query(self) -> bool:
        return self.schema in {"QUERY", "QUERY_LIMIT"}

    @property
    def takes_limit(self) -> bool:
        return self.schema in {"LIMIT", "QUERY_LIMIT"} or self.takes_scan_id

    @property
    def ignores_limit(self) -> bool:
        return self.schema == "QUERY"

    @property
    def path(self) -> tuple[str, ...]:
        return tuple(self.command.split(" "))


_bundled: "Manifest | None" = None


@dataclass(frozen=True)
class Manifest:
    tools: tuple[ManifestTool, ...]
    _by_name: dict[str, ManifestTool] = field(init=False, repr=False, compare=False)
    _command_specs: tuple[tuple[tuple[str, ...], ManifestTool], ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_name", {tool.name: tool for tool in self.tools})
        object.__setattr__(self, "_command_specs", tuple((tool.path, tool) for tool in self.tools))

    @property
    def command_specs(self) -> tuple[tuple[tuple[str, ...], ManifestTool], ...]:
        return self._command_specs

    @classmethod
    def bundled(cls) -> "Manifest":
        """Read once: the packaged file does not change while the process runs."""
        global _bundled
        if _bundled is None:
            _bundled = cls._read()
        return _bundled

    @classmethod
    def _read(cls) -> "Manifest":
        data = json.loads(files("sharpit.cli").joinpath("tools.json").read_text(encoding="utf-8"))
        return cls(
            tuple(
                ManifestTool(
                    name=item["name"],
                    command=item["command"],
                    schema=item["schema"],
                    panel=item["panel"],
                    action=item["action"],
                    summary=item["summary"],
                    description=item["description"],
                    example=item["example"],
                    arguments=tuple(item["arguments"]),
                    required=tuple(item["required"]),
                )
                for item in data["tools"]
            )
        )

    def by_name(self, name: str) -> ManifestTool | None:
        return self._by_name.get(name)
