from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.paging import parse_int_param
from sharpit.engine.sensors.floor import (
    body_field,
    code_paths_beans,
    code_paths_probes,
    code_paths_report,
    code_paths_request,
    code_paths_route,
    start_probe,
    stop_probe,
)
from sharpit.fastapi.http import error, json_response
from sharpit.fastapi.routes.java_agent import PAYLOAD_TOO_LARGE, answer, read_body


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def report(_request: Request) -> Response:
        return json_response(code_paths_report())

    def route(request: Request) -> Response:
        query = request.query_params
        parse_int_param(query.get("offset"), "offset")  # validated as BootUI's Integer binding does
        depth = parse_int_param(query.get("depth"), "depth")
        limit = parse_int_param(query.get("limit"), "limit")
        return json_response(code_paths_route(query.get("route"), depth, limit))

    def beans(_request: Request) -> Response:
        return json_response(code_paths_beans())

    def request_tree(request: Request) -> Response:
        return json_response(code_paths_request(request.path_params["id"]))

    def probes(_request: Request) -> Response:
        return json_response(code_paths_probes())

    async def start(request: Request) -> Response:
        raw = await read_body(ctx, request)
        if raw is None:
            return error(413, PAYLOAD_TOO_LARGE)
        return answer(lambda: start_probe(body_field(raw, "method")))

    def stop(request: Request) -> Response:
        return answer(lambda: stop_probe(request.path_params["id"]))

    return [
        Route(f"{api}/code-paths", report, methods=["GET"]),
        Route(f"{api}/code-paths/route", route, methods=["GET"]),
        Route(f"{api}/code-paths/beans", beans, methods=["GET"]),
        Route(f"{api}/code-paths/requests/{{id}}", request_tree, methods=["GET"]),
        Route(f"{api}/code-paths/probes", probes, methods=["GET"]),
        Route(f"{api}/code-paths/probes", start, methods=["POST"]),
        Route(f"{api}/code-paths/probes/{{id}}/stop", stop, methods=["POST"]),
        Route(f"{api}/code-paths/probes/{{id}}", stop, methods=["GET", "DELETE"]),
    ]
