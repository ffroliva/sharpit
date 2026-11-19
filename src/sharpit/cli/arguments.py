"""Build only declared tool arguments for a CLI invocation."""

from __future__ import annotations

from collections.abc import Mapping

from sharpit.cli.fail_on import Criterion, effective_query
from sharpit.cli.manifest import ManifestTool


def build_tool_arguments(
    tool: ManifestTool,
    options: Mapping[str, object],
    criterion: Criterion | None = None,
) -> dict[str, object]:
    allowed = set(tool.arguments)
    query = options.get("query")
    effective = effective_query(tool.name, str(query) if query is not None else None, criterion)
    result = {
        name: value for name, value in options.items() if name in allowed and value is not None and name != "query"
    }
    if "query" in allowed and effective is not None:
        result["query"] = effective
    return result
