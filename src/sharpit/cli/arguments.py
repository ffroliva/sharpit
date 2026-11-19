"""Build only declared tool arguments for a CLI invocation."""

from __future__ import annotations

from collections.abc import Mapping

from sharpit.cli.fail_on import Criterion, effective_query
from sharpit.cli.manifest import ManifestTool

_WIRE_NAMES = {"scan_id": "scanId"}


def build_tool_arguments(
    tool: ManifestTool,
    options: Mapping[str, object],
    criterion: Criterion | None = None,
) -> dict[str, object]:
    allowed = set(tool.arguments)
    query = options.get("query")
    effective = effective_query(tool.name, str(query) if query is not None else None, criterion)
    result: dict[str, object] = {}
    for name, value in options.items():
        wire_name = _WIRE_NAMES.get(name, name)
        if wire_name in allowed and value is not None and wire_name != "query":
            result[wire_name] = value
    if "query" in allowed and effective is not None:
        result["query"] = effective
    return result
