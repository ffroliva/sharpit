"""Include the offline documentation catalog in standard wheels."""

import ast
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class DocsBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        if version == "editable":
            return
        root = Path(self.root)
        catalog = root / "src/sharpit/cli/docs_catalog.py"
        tree = ast.parse(catalog.read_text(encoding="utf-8"), filename=str(catalog))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "TOPICS" for target in node.targets
            ):
                topics = ast.literal_eval(node.value)
                break
        else:
            raise ValueError("Documentation catalog has no TOPICS declaration")
        if not topics:
            raise ValueError("Documentation catalog is empty")

        for relative_path, _, _ in topics.values():
            page = root / relative_path
            if not page.is_file():
                raise ValueError(f"Documentation catalog file is missing: {relative_path}")
            build_data["force_include"][str(page)] = f"sharpit/_docs/{relative_path}"
