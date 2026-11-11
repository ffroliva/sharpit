from pathlib import Path
from typing import Any

from starlette.routing import Route

from sharpit.engine.collectors.github.dashboard import GitHubDashboard
from sharpit.fastapi.routes import json_response


def build_routes(ctx: Any, _host_app: Any = None) -> list[Any]:
    def report(_request: Any) -> Any:
        return json_response(GitHubDashboard(Path.cwd, ctx.settings).dashboard())

    return [Route(f"{ctx.settings.api_path[len(ctx.settings.path) :]}/github", report, methods=["GET"])]
