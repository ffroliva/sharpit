from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.collectors.metrics import metric_detail, metrics_report
from sharpit.fastapi.routes import json_response

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext


def build_routes(ctx: SharpitContext, _host_app: Any = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def report(request: Request) -> Response:
        p = request.query_params
        try:
            return json_response(
                metrics_report(
                    ctx,
                    p.get("q"),
                    p.get("type"),
                    p.get("group"),
                    p.get("provenance"),
                    p.get("explanation"),
                    p.get("offset"),
                    p.get("limit"),
                )
            )
        except ValueError as exc:
            return json_response({"error": str(exc)}, 400)

    def detail(request: Request) -> Response:
        p = request.query_params
        try:
            return json_response(metric_detail(ctx, p.get("name"), p.getlist("tag"), p.get("offset"), p.get("limit")))
        except ValueError as exc:
            return json_response({"error": str(exc)}, 400)

    return [Route(f"{api}/metrics", report, methods=["GET"]), Route(f"{api}/metrics/detail", detail, methods=["GET"])]
