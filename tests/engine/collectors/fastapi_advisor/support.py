"""Build an app package on disk and load its functions without importing it (compiled with their real file names)."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import Any

from sharpit.engine.appsource import SourceIndex, build_index


def load_app(tmp_path: Path, source: str, name: str = "main") -> tuple[dict[str, Any], Path, SourceIndex]:
    """Write ``<tmp>/app_pkg/<name>.py``, exec it under its real path; return its namespace, the root and its index."""
    root = tmp_path / "app_pkg"
    root.mkdir(exist_ok=True)
    (root / "__init__.py").write_text("", encoding="utf-8")
    path = root / f"{name}.py"
    text = textwrap.dedent(source)
    path.write_text(text, encoding="utf-8")
    namespace: dict[str, Any] = {"__name__": f"app_pkg.{name}"}
    exec(compile(text, os.path.realpath(path), "exec"), namespace)  # noqa: S102 - the test's own fixture source
    return namespace, root, build_index(root, thread=False)
