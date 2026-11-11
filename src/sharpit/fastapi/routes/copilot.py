from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.collectors.agentsessions import Layout, session_store
from sharpit.engine.paging import parse_int_param
from sharpit.fastapi.routes import json_response

if TYPE_CHECKING:
    from starlette.requests import Request

    from sharpit.engine.context import SharpitContext


def build_routes(ctx: SharpitContext, _host_app: object = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]
    prefix = f"{api}/copilot"

    def sessions(request: Request) -> Response:
        store = session_store(ctx, Layout.COPILOT)
        since = parse_int_param(request.query_params.get("since"), "since")
        until = parse_int_param(request.query_params.get("until"), "until")
        return json_response(store.sessions(since, until))

    def dashboard(_request: Request) -> Response:
        store = session_store(ctx, Layout.COPILOT)
        return json_response(store.dashboard())

    def session_detail(request: Request) -> Response:
        store = session_store(ctx, Layout.COPILOT)
        session_id = request.path_params["id"]
        detail = store.detail(session_id)
        if detail is None:
            return Response(status_code=404)
        return json_response(detail)

    def session_events(request: Request) -> Response:
        store = session_store(ctx, Layout.COPILOT)
        session_id = request.path_params["id"]
        if store.detail(session_id) is None:
            return Response(status_code=404)
        category = request.query_params.get("category")
        since = parse_int_param(request.query_params.get("since"), "since")
        limit_param = parse_int_param(request.query_params.get("limit"), "limit")
        limit = 200 if limit_param is None else limit_param
        events_dto = store.events(session_id, category, since, limit)
        if events_dto is None:
            return Response(status_code=404)
        return json_response(events_dto)

    def raw_event(request: Request) -> Response:
        store = session_store(ctx, Layout.COPILOT)
        session_id = request.path_params["id"]
        event_id = request.path_params["eventId"]
        res = store.raw(session_id, event_id)
        if res is None:
            return Response(status_code=404)
        return json_response(res)

    return [
        Route(f"{prefix}/sessions", sessions, methods=["GET"]),
        Route(f"{prefix}/dashboard", dashboard, methods=["GET"]),
        Route(f"{prefix}/sessions/{{id}}", session_detail, methods=["GET"]),
        Route(f"{prefix}/sessions/{{id}}/events", session_events, methods=["GET"]),
        Route(f"{prefix}/sessions/{{id}}/events/{{eventId}}/raw", raw_event, methods=["GET"]),
    ]
