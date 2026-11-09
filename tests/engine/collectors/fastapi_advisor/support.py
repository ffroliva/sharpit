"""Build an app package on disk and load its functions without importing it (compiled with their real file names)."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import Any

from sharpit.engine.advisors.scan import Evaluation
from sharpit.engine.appsource import SourceIndex, build_index
from sharpit.engine.collectors.fastapi_advisor.handlers import Endpoint
from sharpit.engine.collectors.fastapi_advisor.report import evaluate


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


def run_rules(
    tmp_path: Path,
    source: str,
    routes: dict[str, str],
    app: object = None,
    response_models: dict[str, object] | None = None,
) -> Evaluation:
    """Load ``source``, route ``{label: function name}`` to its functions and evaluate every rule on it."""
    namespace, _, index = load_app(tmp_path, source)
    models = response_models or {}
    endpoints = [Endpoint(label, namespace[name], models.get(label)) for label, name in routes.items()]
    return evaluate(app, endpoints, index)


def messages(evaluation: Evaluation, rule_id: str) -> list[str]:
    return [f.message for f in evaluation.findings if f.rule_id == rule_id]
